package service

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/parser"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
)

type CreateSubscriptionInput struct {
	Name          string            `json:"name"`
	URL           string            `json:"url"`
	UserAgent     string            `json:"userAgent,omitempty"`
	Headers       map[string]string `json:"headers,omitempty"`
	UpdateMinutes int               `json:"updateMinutes"`
}

func (s *WorkspaceService) RenameSubscription(id, name string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	name = strings.TrimSpace(name)
	if name == "" {
		return domain.Workspace{}, errors.New("subscription name is required")
	}
	candidate := cloneWorkspace(s.state)
	for i := range candidate.Subscriptions {
		if candidate.Subscriptions[i].ID == id {
			candidate.Subscriptions[i].Name = name
			return s.commit(candidate)
		}
	}
	return domain.Workspace{}, fmt.Errorf("subscription %q does not exist", id)
}

func (s *WorkspaceService) SetSubscriptionEnabled(id string, enabled bool) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	for i := range candidate.Subscriptions {
		if candidate.Subscriptions[i].ID == id {
			candidate.Subscriptions[i].Enabled = enabled
			return s.commit(candidate)
		}
	}
	return domain.Workspace{}, fmt.Errorf("subscription %q does not exist", id)
}

func (s *WorkspaceService) CreateSubscription(input CreateSubscriptionInput) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if strings.TrimSpace(input.Name) == "" || strings.TrimSpace(input.URL) == "" {
		return domain.Workspace{}, errors.New("subscription name and URL are required")
	}
	parsedURL, parseErr := url.ParseRequestURI(strings.TrimSpace(input.URL))
	if parseErr != nil || (parsedURL.Scheme != "https" && parsedURL.Scheme != "http") || parsedURL.Host == "" {
		return domain.Workspace{}, errors.New("subscription URL must be an absolute HTTP or HTTPS URL")
	}
	if s.secrets == nil || !s.secrets.Available() {
		return domain.Workspace{}, errors.New("OS credential vault is required to save subscription URLs")
	}
	id, err := newID()
	if err != nil {
		return domain.Workspace{}, err
	}
	refs := []string{}
	put := func(value string) (string, error) {
		if value == "" {
			return "", nil
		}
		ref, err := newID()
		if err != nil {
			return "", err
		}
		if err := s.secrets.Put(context.Background(), ref, value); err != nil {
			return "", err
		}
		refs = append(refs, ref)
		return ref, nil
	}
	urlRef, err := put(strings.TrimSpace(input.URL))
	if err != nil {
		return domain.Workspace{}, err
	}
	headerRefs := map[string]string{}
	for key, value := range input.Headers {
		ref, putErr := put(value)
		if putErr != nil {
			for _, created := range refs {
				_ = s.secrets.Delete(context.Background(), created)
			}
			return domain.Workspace{}, putErr
		}
		if ref != "" {
			headerRefs[key] = ref
		}
	}
	interval := input.UpdateMinutes
	if interval < 5 {
		interval = 60
	}
	candidate := cloneWorkspace(s.state)
	candidate.Subscriptions = append(candidate.Subscriptions, domain.Subscription{ID: id, Name: strings.TrimSpace(input.Name), URLSecretRef: urlRef, Format: "auto", Enabled: true, UpdateMinutes: interval, UserAgent: input.UserAgent, HeaderSecretRefs: headerRefs})
	result, err := s.commit(candidate)
	if err != nil {
		for _, created := range refs {
			_ = s.secrets.Delete(context.Background(), created)
		}
	}
	return result, err
}

func (s *WorkspaceService) DeleteSubscription(id string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	index := -1
	var removed domain.Subscription
	removedNodes := []domain.Node{}
	for _, node := range candidate.Nodes {
		if node.SourceID == id {
			removedNodes = append(removedNodes, node)
		}
	}
	for i, item := range candidate.Subscriptions {
		if item.ID == id {
			index = i
			removed = item
			break
		}
	}
	if index < 0 {
		return domain.Workspace{}, fmt.Errorf("subscription %q does not exist", id)
	}
	candidate.Subscriptions = append(candidate.Subscriptions[:index], candidate.Subscriptions[index+1:]...)
	for i := range candidate.Nodes {
		if candidate.Nodes[i].GroupID == id {
			candidate.Nodes[i].GroupID = ""
		}
	}
	usedByChain := map[string]bool{}
	for _, chain := range candidate.Chains {
		for _, hop := range chain.HopNodeIDs {
			usedByChain[hop] = true
		}
	}
	nodes := candidate.Nodes[:0]
	for _, node := range candidate.Nodes {
		if node.SourceID != id {
			nodes = append(nodes, node)
			continue
		}
		if usedByChain[node.ID] {
			node.SourceID = ""
			node.Tags = appendUnique(node.Tags, "detached-subscription")
			nodes = append(nodes, node)
		}
	}
	candidate.Nodes = nodes
	removedNodeIDs := map[string]bool{}
	for _, node := range removedNodes {
		removedNodeIDs[node.ID] = true
	}
	if removedNodeIDs[candidate.ActiveNodeID] {
		candidate.ActiveNodeID = ""
	}
	if candidate.TUN.Kind == domain.TUNBindingNode && removedNodeIDs[candidate.TUN.TargetID] {
		candidate.TUN = domain.TUNBinding{Kind: domain.TUNBindingNone}
	}
	result, err := s.commit(candidate)
	if err == nil && s.secrets != nil {
		refs := []string{removed.URLSecretRef}
		for _, ref := range removed.HeaderSecretRefs {
			refs = append(refs, ref)
		}
		for _, ref := range refs {
			if ref != "" {
				_ = s.secrets.Delete(context.Background(), ref)
			}
		}
		for _, node := range removedNodes {
			if !usedByChain[node.ID] {
				deleteNodeSecrets(s.secrets, node)
			}
		}
	}
	return result, err
}

func (s *WorkspaceService) RefreshSubscription(id string) (result domain.Workspace, resultErr error) {
	s.mu.Lock()
	if s.refreshingSubscriptions == nil {
		s.refreshingSubscriptions = map[string]*subscriptionRefreshCall{}
	}
	if call := s.refreshingSubscriptions[id]; call != nil {
		done := call.done
		s.mu.Unlock()
		<-done
		s.mu.RLock()
		workspace := cloneWorkspace(s.state)
		refreshErr := call.err
		s.mu.RUnlock()
		return workspace, refreshErr
	}
	if s.secrets == nil || !s.secrets.Available() {
		s.mu.Unlock()
		return domain.Workspace{}, errors.New("OS credential vault is unavailable")
	}
	var sub domain.Subscription
	found := false
	for _, item := range s.state.Subscriptions {
		if item.ID == id {
			sub = item
			found = true
			break
		}
	}
	if !found {
		s.mu.Unlock()
		return domain.Workspace{}, fmt.Errorf("subscription %q does not exist", id)
	}
	call := &subscriptionRefreshCall{done: make(chan struct{})}
	s.refreshingSubscriptions[id] = call
	secrets := s.secrets
	parent := s.appContext
	if parent == nil {
		parent = context.Background()
	}
	s.mu.Unlock()

	urlValue := ""
	newNodes := []domain.Node{}
	oldNodes := []domain.Node{}
	committed := false
	defer func() {
		if !committed {
			for _, node := range newNodes {
				deleteNodeSecrets(secrets, node)
			}
		}
		s.mu.Lock()
		delete(s.refreshingSubscriptions, id)
		if resultErr != nil {
			candidate := cloneWorkspace(s.state)
			for i := range candidate.Subscriptions {
				if candidate.Subscriptions[i].ID == id {
					errorText := resultErr.Error()
					if urlValue != "" {
						errorText = strings.ReplaceAll(errorText, urlValue, "[subscription URL]")
					}
					candidate.Subscriptions[i].LastError = errorText
					resultErr = errors.New(errorText)
					candidate.Subscriptions[i].LastAttempt = time.Now().UTC().Format(time.RFC3339)
					_, _ = s.commit(candidate)
					break
				}
			}
		}
		call.err = resultErr
		delete(s.refreshingSubscriptions, id)
		close(call.done)
		s.mu.Unlock()
	}()

	var err error
	urlValue, err = secrets.Get(parent, sub.URLSecretRef)
	if err != nil {
		return domain.Workspace{}, fmt.Errorf("resolve subscription URL: %w", err)
	}
	requestCtx, cancel := context.WithTimeout(parent, 45*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(requestCtx, http.MethodGet, urlValue, nil)
	if err != nil {
		return domain.Workspace{}, err
	}
	userAgent := sub.UserAgent
	if userAgent == "" {
		userAgent = "v2rayN/7 ChainPort-Gateway"
	}
	req.Header.Set("User-Agent", userAgent)
	for key, ref := range sub.HeaderSecretRefs {
		value, getErr := secrets.Get(requestCtx, ref)
		if getErr != nil {
			return domain.Workspace{}, fmt.Errorf("resolve subscription header %q: %w", key, getErr)
		}
		req.Header.Set(key, value)
	}
	client := &http.Client{Timeout: 45 * time.Second, CheckRedirect: func(request *http.Request, via []*http.Request) error {
		if len(via) > 0 && (request.URL.Scheme != via[0].URL.Scheme || !strings.EqualFold(request.URL.Host, via[0].URL.Host)) {
			return http.ErrUseLastResponse
		}
		if len(via) >= 5 {
			return errors.New("subscription redirect limit exceeded")
		}
		return nil
	}}
	response, err := client.Do(req)
	if err != nil {
		return domain.Workspace{}, fmt.Errorf("fetch subscription: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return domain.Workspace{}, fmt.Errorf("subscription server returned HTTP %d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 20*1024*1024+1))
	if err != nil {
		return domain.Workspace{}, err
	}
	if len(body) > 20*1024*1024 {
		return domain.Workspace{}, errors.New("subscription response exceeds 20 MiB limit")
	}
	text, format := decodeSubscriptionPayload(body, response.Header.Get("Content-Type"))
	var parseErrors []error
	if format == "clash-yaml" {
		newNodes, parseErrors = parser.ParseClashYAML(requestCtx, text, id, secrets)
	} else {
		if !strings.Contains(text, "://") {
			return domain.Workspace{}, fmt.Errorf("subscription endpoint returned an unrecognized payload (HTTP 200, content-type %q, %d bytes); expected base64/share links or Clash YAML", response.Header.Get("Content-Type"), len(body))
		}
		newNodes, parseErrors = parser.ParseShareLinks(requestCtx, text, id, secrets)
	}
	if len(newNodes) == 0 {
		return domain.Workspace{}, fmt.Errorf("subscription parsed no usable nodes (%d parse errors)", len(parseErrors))
	}

	s.mu.Lock()
	candidate := cloneWorkspace(s.state)
	index := -1
	for i, item := range candidate.Subscriptions {
		if item.ID == id {
			index = i
			break
		}
	}
	if index < 0 {
		s.mu.Unlock()
		return domain.Workspace{}, fmt.Errorf("subscription %q was deleted while it was refreshing", id)
	}
	for _, node := range candidate.Nodes {
		if node.SourceID == id {
			oldNodes = append(oldNodes, node)
		}
	}
	newNodes, oldNodes, staleNodes, reconcileErr := reconcileSubscriptionNodes(oldNodes, newNodes, candidate.Chains, secrets)
	if reconcileErr != nil {
		s.mu.Unlock()
		return domain.Workspace{}, fmt.Errorf("reconcile subscription nodes: %w", reconcileErr)
	}
	kept := candidate.Nodes[:0]
	for _, node := range candidate.Nodes {
		if node.SourceID != id {
			kept = append(kept, node)
		}
	}
	candidate.Nodes = append(kept, newNodes...)
	candidate.Nodes = append(candidate.Nodes, staleNodes...)
	candidate.Subscriptions[index].NodeCount = len(newNodes)
	candidate.Subscriptions[index].LastUpdated = time.Now().UTC().Format(time.RFC3339)
	candidate.Subscriptions[index].LastAttempt = candidate.Subscriptions[index].LastUpdated
	candidate.Subscriptions[index].LastError = ""
	candidate.Subscriptions[index].ParseErrorCount = len(parseErrors)
	candidate.Subscriptions[index].Format = format
	result, resultErr = s.commit(candidate)
	if resultErr == nil {
		committed = true
	}
	s.mu.Unlock()
	if resultErr == nil {
		for _, node := range oldNodes {
			deleteNodeSecrets(secrets, node)
		}
	}
	return result, resultErr
}

func reconcileSubscriptionNodes(existing, incoming []domain.Node, chains []domain.Chain, secrets security.SecretStore) ([]domain.Node, []domain.Node, []domain.Node, error) {
	buckets := map[string][]domain.Node{}
	for _, node := range existing {
		key, err := subscriptionNodeKey(node, secrets)
		if err != nil {
			return nil, nil, nil, err
		}
		buckets[key] = append(buckets[key], node)
	}
	matchedOld := []domain.Node{}
	for i := range incoming {
		key, err := subscriptionNodeKey(incoming[i], secrets)
		if err != nil {
			return nil, nil, nil, err
		}
		bucket := buckets[key]
		if len(bucket) == 0 {
			continue
		}
		previous := bucket[0]
		buckets[key] = bucket[1:]
		incoming[i].ID = previous.ID
		// Keep a user's explicit move into a custom group when refreshing the
		// subscription. Empty or source-owned assignments remain unchanged.
		incoming[i].GroupID = previous.GroupID
		for _, tag := range previous.Tags {
			incoming[i].Tags = appendUnique(incoming[i].Tags, tag)
		}
		matchedOld = append(matchedOld, previous)
	}
	used := map[string]bool{}
	for _, chain := range chains {
		for _, id := range chain.HopNodeIDs {
			used[id] = true
		}
	}
	obsolete := append([]domain.Node(nil), matchedOld...)
	stale := []domain.Node{}
	for _, bucket := range buckets {
		for _, node := range bucket {
			if used[node.ID] {
				node.Tags = appendUnique(node.Tags, "stale-subscription-node")
				stale = append(stale, node)
			} else {
				obsolete = append(obsolete, node)
			}
		}
	}
	return incoming, obsolete, stale, nil
}

func subscriptionNodeKey(node domain.Node, secrets security.SecretStore) (string, error) {
	parts := []string{string(node.Protocol), strings.ToLower(node.Server), fmt.Sprint(node.Port), strings.ToLower(node.Transport.Network), strings.ToLower(node.Transport.Host), node.Transport.Path, strings.ToLower(node.TLS.SNI), node.Flow, node.Cipher, node.Security, node.WGPublicKey}
	if secrets == nil && (node.Credentials.UUIDRef != "" || node.Credentials.UsernameRef != "" || node.Credentials.PasswordRef != "" || node.Credentials.PrivateKeyRef != "") {
		return "", security.ErrUnavailable
	}
	for _, reference := range []string{node.Credentials.UUIDRef, node.Credentials.UsernameRef, node.Credentials.PasswordRef, node.Credentials.PrivateKeyRef} {
		if reference == "" {
			parts = append(parts, "")
			continue
		}
		value, err := secrets.Get(context.Background(), reference)
		if err != nil {
			return "", fmt.Errorf("resolve credential while matching refreshed node %q: %w", node.ID, err)
		}
		parts = append(parts, value)
	}
	return strings.Join(parts, "\x00"), nil
}
func appendUnique(values []string, value string) []string {
	for _, existing := range values {
		if existing == value {
			return values
		}
	}
	return append(values, value)
}

func deleteNodeSecrets(secrets interface {
	Delete(context.Context, string) error
}, node domain.Node) {
	for _, ref := range []string{node.Credentials.UsernameRef, node.Credentials.PasswordRef, node.Credentials.UUIDRef, node.Credentials.PrivateKeyRef, node.SourceMetadataRef} {
		if ref != "" {
			_ = secrets.Delete(context.Background(), ref)
		}
	}
}

func (s *WorkspaceService) RefreshAllSubscriptions() (domain.Workspace, []string, error) {
	s.mu.RLock()
	ids := make([]string, 0, len(s.state.Subscriptions))
	for _, sub := range s.state.Subscriptions {
		if sub.Enabled {
			ids = append(ids, sub.ID)
		}
	}
	s.mu.RUnlock()
	var failures []string
	for _, id := range ids {
		if _, err := s.RefreshSubscription(id); err != nil {
			failures = append(failures, err.Error())
		}
	}
	return s.GetWorkspace(), failures, nil
}

func decodeSubscriptionPayload(body []byte, contentType string) (string, string) {
	text := strings.TrimSpace(strings.TrimPrefix(string(body), "\ufeff"))
	if strings.Contains(strings.ToLower(contentType), "yaml") || strings.HasPrefix(text, "proxies:") || strings.HasPrefix(text, "port:") {
		return text, "clash-yaml"
	}
	if !strings.Contains(text, "://") {
		if decoded, err := decodeSubscriptionBase64(text); err == nil {
			candidate := strings.TrimSpace(string(decoded))
			candidate = strings.TrimSpace(strings.TrimPrefix(candidate, "\ufeff"))
			if strings.Contains(candidate, "://") || strings.HasPrefix(candidate, "proxies:") || strings.HasPrefix(candidate, "port:") {
				text = candidate
			}
		}
	}
	if strings.HasPrefix(text, "proxies:") || strings.HasPrefix(text, "port:") {
		return text, "clash-yaml"
	}
	return text, "share-links"
}

func decodeSubscriptionBase64(value string) ([]byte, error) {
	for _, encoding := range []*base64.Encoding{base64.StdEncoding, base64.RawStdEncoding, base64.URLEncoding, base64.RawURLEncoding} {
		decoded, err := encoding.DecodeString(value)
		if err == nil {
			return decoded, nil
		}
	}
	return nil, errors.New("subscription body is not valid standard or URL-safe base64")
}
