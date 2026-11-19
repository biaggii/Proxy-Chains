package service

import (
	"context"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
)

type subscriptionSecrets map[string]string

func (s subscriptionSecrets) Available() bool                                 { return true }
func (s subscriptionSecrets) Put(_ context.Context, k, v string) error        { s[k] = v; return nil }
func (s subscriptionSecrets) Get(_ context.Context, k string) (string, error) { return s[k], nil }
func (s subscriptionSecrets) Delete(_ context.Context, k string) error        { delete(s, k); return nil }

func TestSubscriptionCreateRefreshAndDelete(t *testing.T) {
	feed := base64.StdEncoding.EncodeToString([]byte("socks5://feed-user:feed-password@proxy.example:1080#FeedNode"))
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Feed-Key") != "header-secret" {
			t.Errorf("subscription header not resolved")
		}
		w.Header().Set("Content-Type", "text/plain")
		_, _ = w.Write([]byte(feed))
	}))
	defer server.Close()
	store := &memoryStore{workspace: domain.DefaultWorkspace()}
	secrets := subscriptionSecrets{}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), store, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateSubscription(CreateSubscriptionInput{Name: "Test Feed", URL: server.URL, Headers: map[string]string{"X-Feed-Key": "header-secret"}, UpdateMinutes: 30})
	if err != nil {
		t.Fatal(err)
	}
	if len(created.Subscriptions) != 1 || created.Subscriptions[0].URLSecretRef == "" {
		t.Fatal("subscription URL not stored as secret reference")
	}
	id := created.Subscriptions[0].ID
	refreshed, err := service.RefreshSubscription(id)
	if err != nil {
		t.Fatal(err)
	}
	if len(refreshed.Nodes) != 1 || refreshed.Nodes[0].SourceID != id || refreshed.Subscriptions[0].NodeCount != 1 {
		t.Fatalf("subscription nodes not imported: %+v", refreshed)
	}
	if secrets[refreshed.Nodes[0].Credentials.UsernameRef] != "feed-user" || secrets[refreshed.Nodes[0].Credentials.PasswordRef] != "feed-password" {
		t.Fatal("node credentials were not stored in credential vault")
	}
	deleted, err := service.DeleteSubscription(id)
	if err != nil {
		t.Fatal(err)
	}
	if len(deleted.Subscriptions) != 0 || len(deleted.Nodes) != 0 {
		t.Fatal("subscription deletion did not remove its nodes")
	}
}

func TestDecodeSubscriptionPayloadDetectsClashAndBase64Links(t *testing.T) {
	yamlText, format := decodeSubscriptionPayload([]byte("proxies:\n  - name: a"), "text/plain")
	if format != "clash-yaml" || yamlText == "" {
		t.Fatal("Clash YAML not detected")
	}
	encoded := base64.StdEncoding.EncodeToString([]byte("vless://uuid@example.com:443#node"))
	decoded, format := decodeSubscriptionPayload([]byte(encoded), "text/plain")
	if format != "share-links" || decoded != "vless://uuid@example.com:443#node" {
		t.Fatalf("base64 share link not decoded: %q %s", decoded, format)
	}
}

func TestRefreshPreservesChainReferencesAndDetachesNodesOnSubscriptionDelete(t *testing.T) {
	var body atomic.Value
	body.Store("socks5://u:p@entry.example:1080#Entry\nsocks5://u:p@exit.example:1081#Exit")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = w.Write([]byte(body.Load().(string))) }))
	defer server.Close()
	secrets := subscriptionSecrets{}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: domain.DefaultWorkspace()}, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateSubscription(CreateSubscriptionInput{Name: "Feed", URL: server.URL, UpdateMinutes: 60})
	if err != nil {
		t.Fatal(err)
	}
	refreshed, err := service.RefreshSubscription(created.Subscriptions[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	entryID := refreshed.Nodes[0].ID
	withChain, err := service.CreateChain(CreateChainInput{Name: "Keep Entry", HopNodeIDs: []string{entryID}})
	if err != nil {
		t.Fatal(err)
	}
	body.Store("socks5://u:p@exit.example:1081#Exit")
	refreshed, err = service.RefreshSubscription(created.Subscriptions[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(refreshed.Chains) != 1 || refreshed.Chains[0].HopNodeIDs[0] != entryID {
		t.Fatal("subscription refresh broke an existing Chain reference")
	}
	stale := false
	for _, node := range refreshed.Nodes {
		if node.ID == entryID {
			for _, tag := range node.Tags {
				if tag == "stale-subscription-node" {
					stale = true
				}
			}
		}
	}
	if !stale {
		t.Fatal("removed but chain-referenced node was not retained as stale")
	}
	deleted, err := service.DeleteSubscription(created.Subscriptions[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(deleted.Chains) != 1 || deleted.Chains[0].HopNodeIDs[0] != entryID {
		t.Fatal("deleting subscription removed a node still referenced by a Chain")
	}
	if len(deleted.Nodes) != 1 || deleted.Nodes[0].SourceID != "" {
		t.Fatalf("expected only the detached Chain node to remain: %+v", deleted.Nodes)
	}
	if len(withChain.Chains) != 1 {
		t.Fatal("test setup failed to create Chain")
	}
}

func TestDeleteSubscriptionClearsActiveAndDirectTUNNodeReferences(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("socks5://u:p@node.example:1080#Node"))
	}))
	defer server.Close()
	secrets := subscriptionSecrets{}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: domain.DefaultWorkspace()}, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateSubscription(CreateSubscriptionInput{Name: "Feed", URL: server.URL, UpdateMinutes: 60})
	if err != nil {
		t.Fatal(err)
	}
	refreshed, err := service.RefreshSubscription(created.Subscriptions[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = service.BindTUNToBaseNode(refreshed.Nodes[0].ID); err != nil {
		t.Fatal(err)
	}
	if _, err = service.SetActiveBaseNode(refreshed.Nodes[0].ID); err != nil {
		t.Fatal(err)
	}
	deleted, err := service.DeleteSubscription(created.Subscriptions[0].ID)
	if err != nil {
		t.Fatalf("delete subscription failed while its node was active/TUN-bound: %v", err)
	}
	if deleted.ActiveNodeID != "" || deleted.TUN.Kind != domain.TUNBindingNone || len(deleted.Nodes) != 0 {
		t.Fatalf("dangling node references remain after subscription deletion: %+v", deleted)
	}
}

func TestConcurrentSubscriptionRefreshesShareOneInFlightRequest(t *testing.T) {
	var requests atomic.Int32
	entered := make(chan struct{}, 2)
	release := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		entered <- struct{}{}
		<-release
		_, _ = w.Write([]byte("socks5://u:p@node.example:1080#Node"))
	}))
	defer server.Close()
	secrets := subscriptionSecrets{}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: domain.DefaultWorkspace()}, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateSubscription(CreateSubscriptionInput{Name: "Feed", URL: server.URL, UpdateMinutes: 60})
	if err != nil {
		t.Fatal(err)
	}
	type result struct {
		workspace domain.Workspace
		err       error
	}
	results := make(chan result, 2)
	go func() { w, e := service.RefreshSubscription(created.Subscriptions[0].ID); results <- result{w, e} }()
	select {
	case <-entered:
	case <-time.After(2 * time.Second):
		t.Fatal("first refresh did not reach HTTP server")
	}
	go func() { w, e := service.RefreshSubscription(created.Subscriptions[0].ID); results <- result{w, e} }()
	time.Sleep(30 * time.Millisecond)
	close(release)
	for i := 0; i < 2; i++ {
		select {
		case got := <-results:
			if got.err != nil {
				t.Fatalf("coalesced refresh returned error: %v", got.err)
			}
			if len(got.workspace.Nodes) != 1 {
				t.Fatalf("coalesced refresh returned incomplete workspace: %d nodes", len(got.workspace.Nodes))
			}
		case <-time.After(3 * time.Second):
			t.Fatal("coalesced refresh did not finish")
		}
	}
	if requests.Load() != 1 {
		t.Fatalf("expected exactly one HTTP request for overlapping refreshes, got %d", requests.Load())
	}
}

func TestDecodeSubscriptionPayloadAcceptsBase64URLAndUTF8BOM(t *testing.T) {
	plain := []byte("vless://user@example.com:443#Node\n")
	encoded := base64.RawURLEncoding.EncodeToString(append([]byte{0xef, 0xbb, 0xbf}, plain...))
	decoded, format := decodeSubscriptionPayload([]byte(encoded), "application/octet-stream")
	if format != "share-links" || !strings.HasPrefix(decoded, "vless://") {
		t.Fatalf("URL-safe base64/BOM payload was not detected: format=%q payload=%q", format, decoded)
	}
}

func TestDecodeSubscriptionPayloadDetectsClashYAMLWithBOM(t *testing.T) {
	decoded, format := decodeSubscriptionPayload([]byte("\xef\xbb\xbfproxies:\n  - name: Node\n"), "text/plain")
	if format != "clash-yaml" || !strings.HasPrefix(decoded, "proxies:") {
		t.Fatalf("BOM-prefixed Clash YAML was not detected: format=%q", format)
	}
}

func TestRefreshPreservesNodeIdentityWhenFeedRenamesEntry(t *testing.T) {
	var body atomic.Value
	body.Store("socks5://user:password@entry.example:1080#Original")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = w.Write([]byte(body.Load().(string))) }))
	defer server.Close()
	secrets := subscriptionSecrets{}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: domain.DefaultWorkspace()}, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateSubscription(CreateSubscriptionInput{Name: "Feed", URL: server.URL, UpdateMinutes: 60})
	if err != nil {
		t.Fatal(err)
	}
	first, err := service.RefreshSubscription(created.Subscriptions[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	id := first.Nodes[0].ID
	body.Store("socks5://user:password@entry.example:1080#Renamed")
	second, err := service.RefreshSubscription(created.Subscriptions[0].ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(second.Nodes) != 1 || second.Nodes[0].ID != id || second.Nodes[0].Name != "Renamed" {
		t.Fatalf("feed rename changed node identity or lost new name: %+v", second.Nodes)
	}
}

func TestRefreshErrorsDoNotLeakSubscriptionURL(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	url := server.URL + "?token=subscription-secret"
	server.Close()
	secrets := subscriptionSecrets{}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: domain.DefaultWorkspace()}, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateSubscription(CreateSubscriptionInput{Name: "Private Feed", URL: url, UpdateMinutes: 60})
	if err != nil {
		t.Fatal(err)
	}
	_, err = service.RefreshSubscription(created.Subscriptions[0].ID)
	if err == nil || strings.Contains(err.Error(), "subscription-secret") {
		t.Fatalf("refresh error leaked subscription URL: %v", err)
	}
	if strings.Contains(service.GetWorkspace().Subscriptions[0].LastError, "subscription-secret") {
		t.Fatal("persisted refresh error leaked subscription URL")
	}
}
