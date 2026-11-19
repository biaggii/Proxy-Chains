package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/autostart"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/core"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/migration"
	runtimecore "github.com/biaggii/Proxy-Chains/go-wails3/internal/runtime"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/tun"
)

type WorkspaceStore interface {
	Load(context.Context) (domain.Workspace, error)
	Save(context.Context, domain.Workspace) error
}

type WorkspaceService struct {
	mu                      sync.RWMutex
	appContext              context.Context
	store                   WorkspaceStore
	state                   domain.Workspace
	secrets                 security.SecretStore
	selectLegacyFile        func() (string, error)
	supervisor              *runtimecore.Supervisor
	configDir               string
	activeConfigPath        string
	schedulerStarted        bool
	refreshingSubscriptions map[string]*subscriptionRefreshCall
}

type subscriptionRefreshCall struct {
	done chan struct{}
	err  error
}

type CreateChainInput struct {
	Name       string   `json:"name"`
	HopNodeIDs []string `json:"hopNodeIds"`
	ListenPort uint16   `json:"listenPort"`
}

type UpdateChainInput struct {
	ID         string   `json:"id"`
	Name       string   `json:"name"`
	HopNodeIDs []string `json:"hopNodeIds"`
	ListenPort uint16   `json:"listenPort"`
}

type CreateNodeInput struct {
	Name     string          `json:"name"`
	Protocol domain.Protocol `json:"protocol"`
	Server   string          `json:"server"`
	Port     uint16          `json:"port"`
	Username string          `json:"username,omitempty"`
	Password string          `json:"password,omitempty"`
	UUID     string          `json:"uuid,omitempty"`
	TLS      bool            `json:"tls"`
	SNI      string          `json:"sni,omitempty"`
	Network  string          `json:"network,omitempty"`
	Path     string          `json:"path,omitempty"`
	Host     string          `json:"host,omitempty"`
}

type UpdateNodeInput struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Server  string `json:"server"`
	Port    uint16 `json:"port"`
	Network string `json:"network"`
	Path    string `json:"path,omitempty"`
	Host    string `json:"host,omitempty"`
	TLS     bool   `json:"tls"`
	SNI     string `json:"sni,omitempty"`
}

func NewWorkspaceService() *WorkspaceService {
	return &WorkspaceService{state: domain.DefaultWorkspace()}
}

func NewWorkspaceServiceWithStore(ctx context.Context, store WorkspaceStore) (*WorkspaceService, error) {
	return NewWorkspaceServiceWithDependencies(ctx, store, nil, nil, nil)
}

func NewWorkspaceServiceWithDependencies(ctx context.Context, store WorkspaceStore, secrets security.SecretStore, selectFile func() (string, error), onRuntimeEvent func(runtimecore.Event)) (*WorkspaceService, error) {
	state, err := store.Load(ctx)
	if err != nil {
		return nil, err
	}
	if err := state.Validate(); err != nil {
		return nil, err
	}
	configDir := state.Settings.ConfigOutputDir
	if configDir == "" {
		base, err := os.UserConfigDir()
		if err != nil {
			return nil, err
		}
		configDir = filepath.Join(base, "ChainPort Gateway", "runtime")
	}
	return &WorkspaceService{appContext: ctx, store: store, state: state, secrets: secrets, selectLegacyFile: selectFile, supervisor: runtimecore.NewSupervisor(onRuntimeEvent), configDir: configDir, refreshingSubscriptions: map[string]*subscriptionRefreshCall{}}, nil
}

func (s *WorkspaceService) ImportLegacyStateFile() (migration.MigrationReport, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var report migration.MigrationReport
	if s.selectLegacyFile == nil {
		return report, errors.New("legacy state file picker is unavailable")
	}
	if s.store == nil {
		return report, errors.New("workspace database is not configured")
	}
	if len(s.state.Nodes)+len(s.state.Chains)+len(s.state.Subscriptions) > 0 {
		return report, errors.New("legacy import is only available in an empty workspace")
	}
	path, err := s.selectLegacyFile()
	if err != nil {
		return report, err
	}
	if path == "" {
		return report, nil
	}
	info, err := os.Stat(path)
	if err != nil {
		return report, fmt.Errorf("inspect selected legacy state file: %w", err)
	}
	if info.Size() > 32*1024*1024 {
		return report, errors.New("legacy state.json exceeds the 32 MiB import limit")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return report, fmt.Errorf("read selected legacy state file: %w", err)
	}
	candidate, report, err := migration.ImportLegacyState(context.Background(), data, s.secrets)
	if err != nil {
		return report, err
	}
	if err := s.store.Save(context.Background(), candidate); err != nil {
		if s.secrets != nil {
			for _, reference := range report.SecretReferences {
				_ = s.secrets.Delete(context.Background(), reference)
			}
		}
		return report, fmt.Errorf("save imported workspace: %w", err)
	}
	s.state = candidate
	if err := autostart.SetEnabled(candidate.Settings.RunOnStartup); err != nil {
		report.Warnings = append(report.Warnings, "Workspace imported, but operating-system startup registration could not be updated: "+err.Error())
	}
	return report, nil
}

func (s *WorkspaceService) GetWorkspace() domain.Workspace {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return cloneWorkspace(s.state)
}

func (s *WorkspaceService) UpdateSettings(settings domain.Settings) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	candidate.Settings = settings
	if err := candidate.Validate(); err != nil {
		return domain.Workspace{}, err
	}
	if s.supervisor != nil && s.supervisor.Snapshot().Status == runtimecore.StatusRunning && settings.Core.Type != s.state.Settings.Core.Type {
		return domain.Workspace{}, errors.New("stop the running core before changing the selected core")
	}
	previousStartup := s.state.Settings.RunOnStartup
	if settings.RunOnStartup != previousStartup {
		if err := autostart.SetEnabled(settings.RunOnStartup); err != nil {
			return domain.Workspace{}, fmt.Errorf("update system startup registration: %w", err)
		}
	}
	result, err := s.commit(candidate)
	if err != nil && settings.RunOnStartup != previousStartup {
		_ = autostart.SetEnabled(previousStartup)
	}
	return result, err
}

func (s *WorkspaceService) SetCoreExecutable(coreName, path string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	coreName = strings.ToLower(strings.TrimSpace(coreName))
	if coreName != "sing-box" && coreName != "xray" && coreName != "mihomo" {
		return domain.Workspace{}, fmt.Errorf("unsupported core %q", coreName)
	}
	if strings.TrimSpace(path) == "" {
		delete(candidate.Settings.Core.Executable, coreName)
	} else {
		candidate.Settings.Core.Executable[coreName] = path
	}
	return s.commit(candidate)
}

func (s *WorkspaceService) GetRuntimeStatus() runtimecore.Snapshot {
	if s.supervisor == nil {
		return runtimecore.Snapshot{Status: runtimecore.StatusStopped}
	}
	return s.supervisor.Snapshot()
}
func (s *WorkspaceService) GetRuntimeLogs() []string {
	if s.supervisor == nil {
		return []string{}
	}
	return s.supervisor.Logs()
}

func (s *WorkspaceService) ClearRuntimeLogs() {
	if s.supervisor != nil {
		s.supervisor.ClearLogs()
	}
}

func (s *WorkspaceService) StartSubscriptionScheduler(ctx context.Context) {
	s.mu.Lock()
	if s.schedulerStarted {
		s.mu.Unlock()
		return
	}
	s.schedulerStarted = true
	s.mu.Unlock()
	go func() {
		ticker := time.NewTicker(time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case now := <-ticker.C:
				s.refreshDueSubscriptions(now)
			}
		}
	}()
}

func (s *WorkspaceService) refreshDueSubscriptions(now time.Time) {
	s.mu.RLock()
	due := []string{}
	for _, sub := range s.state.Subscriptions {
		if !sub.Enabled || sub.UpdateMinutes <= 0 {
			continue
		}
		lastValue := sub.LastAttempt
		if lastValue == "" {
			lastValue = sub.LastUpdated
		}
		if lastValue == "" {
			due = append(due, sub.ID)
			continue
		}
		last, err := time.Parse(time.RFC3339, lastValue)
		interval := time.Duration(maxInt(sub.UpdateMinutes, 5)) * time.Minute
		if sub.LastError != "" {
			interval = 5 * time.Minute
		}
		if err != nil || now.Sub(last) >= interval {
			due = append(due, sub.ID)
		}
	}
	s.mu.RUnlock()
	for _, id := range due {
		_, _ = s.RefreshSubscription(id)
	}
}

func maxInt(value, fallback int) int {
	if value < fallback {
		return fallback
	}
	return value
}

func (s *WorkspaceService) StartCore() (startErr error) {
	if s.supervisor != nil {
		defer func() {
			if startErr != nil {
				s.supervisor.AppendLog("Start failed: " + startErr.Error())
			}
		}()
	}
	s.mu.RLock()
	workspace := cloneWorkspace(s.state)
	configDir := s.configDir
	s.mu.RUnlock()
	if s.supervisor == nil {
		return errors.New("core process supervisor is unavailable")
	}
	coreName := strings.ToLower(workspace.Settings.Core.Type)
	executable := workspace.Settings.Core.Executable[coreName]
	if executable == "" {
		executable = workspace.Settings.Core.Executable[workspace.Settings.Core.Type]
	}
	if executable == "" {
		executable = coreName
	}
	resolvedExecutable, lookErr := exec.LookPath(executable)
	if lookErr != nil {
		return fmt.Errorf("cannot locate %s executable %q; install it or set its path in Settings: %w", coreName, executable, lookErr)
	}
	executable = resolvedExecutable
	generated, err := core.GenerateConfig(context.Background(), workspace, coreName, s.secrets)
	if err != nil {
		return fmt.Errorf("generate core config: %w", err)
	}
	if workspace.TUN.Enabled {
		if ok, reason := tun.HasPrivileges(); !ok {
			return errors.New(reason)
		}
	}
	configPath, err := runtimecore.WriteConfig(configDir, "chainport_config"+generated.Extension, generated.Data)
	if err != nil {
		return err
	}
	started := false
	defer func() {
		if !started {
			_ = os.Remove(configPath)
		}
	}()
	checkCommand, startCommand, err := coreCommands(coreName, executable, configPath)
	if err != nil {
		return err
	}
	var redactions []string
	for _, node := range workspace.Nodes {
		resolved, resolveErr := core.ResolveNode(context.Background(), node, s.secrets)
		if resolveErr != nil {
			return fmt.Errorf("resolve node secrets before starting core: %w", resolveErr)
		}
		redactions = append(redactions, resolved.Username, resolved.Password, resolved.UUID, resolved.PrivateKey)
		redactions = append(redactions, metadataStrings(resolved.Extra)...)
	}
	s.supervisor.AppendLog("Core executable: " + executable)
	versionArgs := coreVersionArgs(coreName, executable)
	versionCtx, versionCancel := context.WithTimeout(context.Background(), 5*time.Second)
	versionOutput, versionErr := exec.CommandContext(versionCtx, versionArgs[0], versionArgs[1:]...).CombinedOutput()
	versionCancel()
	if versionErr != nil {
		s.supervisor.AppendLog("Core version probe failed: " + versionErr.Error())
	} else if strings.TrimSpace(string(versionOutput)) != "" {
		s.supervisor.AppendLog("Core version: " + strings.TrimSpace(string(versionOutput)))
	}
	checkOutput, err := s.supervisor.RunCheck(context.Background(), checkCommand, redactions)
	if strings.TrimSpace(checkOutput) != "" {
		s.supervisor.AppendLog("Configuration validation output:\n" + strings.TrimSpace(checkOutput))
	}
	if err != nil {
		if strings.TrimSpace(checkOutput) != "" {
			return fmt.Errorf("%w\n%s", err, strings.TrimSpace(checkOutput))
		}
		return err
	}
	s.supervisor.AppendLog(fmt.Sprintf("Configuration validated. Starting %s.", coreName))
	parent := s.appContext
	if parent == nil {
		parent = context.Background()
	}
	if err := s.supervisor.Start(parent, startCommand, redactions); err != nil {
		return err
	}
	s.mu.Lock()
	s.activeConfigPath = configPath
	s.mu.Unlock()
	started = true
	return nil
}

func metadataStrings(value any) []string {
	result := []string{}
	collectMetadataSecrets(value, "", &result)
	return result
}

func collectMetadataSecrets(value any, key string, result *[]string) {
	normalized := strings.ToLower(strings.NewReplacer("-", "", "_", "", " ", "").Replace(key))
	sensitive := map[string]bool{"password": true, "pass": true, "username": true, "user": true, "uuid": true, "id": true, "privatekey": true, "secret": true, "secretkey": true, "presharedkey": true, "token": true, "authorization": true, "cookie": true, "apikey": true, "accesskey": true, "credential": true, "credentials": true}
	switch item := value.(type) {
	case string:
		if sensitive[normalized] && item != "" {
			*result = append(*result, item)
		} else if normalized == "extra" && strings.HasPrefix(strings.TrimSpace(item), "{") {
			var decoded any
			if json.Unmarshal([]byte(item), &decoded) == nil {
				collectMetadataSecrets(decoded, "", result)
			}
		}
	case []string:
		for _, part := range item {
			collectMetadataSecrets(part, key, result)
		}
	case []any:
		for _, part := range item {
			collectMetadataSecrets(part, key, result)
		}
	case map[string]any:
		for childKey, part := range item {
			collectMetadataSecrets(part, childKey, result)
		}
	case map[string][]string:
		for childKey, parts := range item {
			collectMetadataSecrets(parts, childKey, result)
		}
	}
}

func (s *WorkspaceService) StopCore() error {
	if s.supervisor == nil {
		return nil
	}
	s.supervisor.AppendLog("Stopping core process.")
	if err := s.supervisor.Stop(); err != nil {
		return err
	}
	s.supervisor.AppendLog("Core process stopped.")
	if status := s.supervisor.Snapshot().Status; status != runtimecore.StatusRunning && status != runtimecore.StatusStarting && status != runtimecore.StatusStopping {
		s.mu.Lock()
		path := s.activeConfigPath
		s.activeConfigPath = ""
		s.mu.Unlock()
		if path != "" {
			_ = os.Remove(path)
		}
	}
	return nil
}

func coreCommands(coreName, executable, configPath string) ([]string, []string, error) {
	switch strings.ToLower(coreName) {
	case "sing-box", "singbox":
		return []string{executable, "check", "-c", configPath}, []string{executable, "run", "-c", configPath}, nil
	case "xray":
		return []string{executable, "run", "-test", "-c", configPath}, []string{executable, "run", "-c", configPath}, nil
	case "mihomo", "clash-meta":
		return []string{executable, "-t", "-f", configPath}, []string{executable, "-f", configPath}, nil
	default:
		return nil, nil, fmt.Errorf("unsupported core %q", coreName)
	}
}

func coreVersionArgs(coreName, executable string) []string {
	switch strings.ToLower(coreName) {
	case "sing-box", "singbox":
		return []string{executable, "version"}
	case "xray":
		return []string{executable, "version"}
	case "mihomo", "clash-meta":
		return []string{executable, "-v"}
	default:
		return []string{executable, "version"}
	}
}

func (s *WorkspaceService) CreateNode(input CreateNodeInput) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if input.Name == "" || input.Server == "" || input.Port == 0 {
		return domain.Workspace{}, errors.New("node name, server and port are required")
	}
	if input.Protocol != domain.ProtocolSOCKS5 && input.Protocol != domain.ProtocolHTTP {
		return domain.Workspace{}, errors.New("manual node creation currently supports SOCKS5 and HTTP")
	}
	candidate := cloneWorkspace(s.state)
	nodeID, err := newID()
	if err != nil {
		return domain.Workspace{}, err
	}
	refs := []string{}
	putSecret := func(value string) (string, error) {
		if value == "" {
			return "", nil
		}
		if s.secrets == nil || !s.secrets.Available() {
			return "", security.ErrUnavailable
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
	usernameRef, err := putSecret(input.Username)
	if err != nil {
		return domain.Workspace{}, err
	}
	passwordRef, err := putSecret(input.Password)
	if err != nil {
		for _, ref := range refs {
			_ = s.secrets.Delete(context.Background(), ref)
		}
		return domain.Workspace{}, err
	}
	uuidRef, err := putSecret(input.UUID)
	if err != nil {
		for _, ref := range refs {
			_ = s.secrets.Delete(context.Background(), ref)
		}
		return domain.Workspace{}, err
	}
	network := input.Network
	if network == "" {
		network = "tcp"
	}
	candidate.Nodes = append(candidate.Nodes, domain.Node{
		ID: nodeID, Name: input.Name, Protocol: input.Protocol, Server: input.Server, Port: input.Port,
		Credentials: domain.Credentials{UsernameRef: usernameRef, PasswordRef: passwordRef, UUIDRef: uuidRef},
		Transport:   domain.Transport{Network: network, Path: input.Path, Host: input.Host}, TLS: domain.TLSOptions{Enabled: input.TLS, SNI: input.SNI},
	})
	result, err := s.commit(candidate)
	if err != nil && s.secrets != nil {
		for _, ref := range refs {
			_ = s.secrets.Delete(context.Background(), ref)
		}
	}
	return result, err
}

// UpdateNode edits public node metadata without exposing or rewriting credentials.
func (s *WorkspaceService) UpdateNode(input UpdateNodeInput) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if strings.TrimSpace(input.Name) == "" || strings.TrimSpace(input.Server) == "" || input.Port == 0 {
		return domain.Workspace{}, errors.New("node name, server and a valid port are required")
	}
	candidate := cloneWorkspace(s.state)
	for i := range candidate.Nodes {
		node := &candidate.Nodes[i]
		if node.ID != input.ID {
			continue
		}
		node.Name = strings.TrimSpace(input.Name)
		node.Server = strings.TrimSpace(input.Server)
		node.Port = input.Port
		if input.Network != "" {
			node.Transport.Network = input.Network
		}
		node.Transport.Path = input.Path
		node.Transport.Host = input.Host
		node.TLS.Enabled = input.TLS
		node.TLS.SNI = input.SNI
		return s.commit(candidate)
	}
	return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", input.ID)
}

func (s *WorkspaceService) DeleteNode(nodeID string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	index := -1
	var removed domain.Node
	for i, node := range candidate.Nodes {
		if node.ID == nodeID {
			index = i
			removed = node
			break
		}
	}
	if index < 0 {
		return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", nodeID)
	}
	for _, chain := range candidate.Chains {
		for _, hop := range chain.HopNodeIDs {
			if hop == nodeID {
				return domain.Workspace{}, fmt.Errorf("Base Node %q is used by Chain %q; remove it from the Chain first", removed.Name, chain.Name)
			}
		}
	}
	candidate.Nodes = append(candidate.Nodes[:index], candidate.Nodes[index+1:]...)
	if candidate.ActiveNodeID == nodeID {
		candidate.ActiveNodeID = ""
	}
	if candidate.TUN.Kind == domain.TUNBindingNode && candidate.TUN.TargetID == nodeID {
		candidate.TUN = domain.TUNBinding{Kind: domain.TUNBindingNone}
	}
	result, err := s.commit(candidate)
	if err == nil && s.secrets != nil {
		for _, ref := range []string{removed.Credentials.UsernameRef, removed.Credentials.PasswordRef, removed.Credentials.UUIDRef, removed.Credentials.PrivateKeyRef, removed.SourceMetadataRef} {
			if ref != "" {
				_ = s.secrets.Delete(context.Background(), ref)
			}
		}
	}
	return result, err
}

func (s *WorkspaceService) CreateChain(input CreateChainInput) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	port := input.ListenPort
	if port == 0 {
		port = nextAvailablePort(candidate)
	}
	if port == 0 {
		return domain.Workspace{}, errors.New("no available local ports remain")
	}
	chainID, err := newID()
	if err != nil {
		return domain.Workspace{}, err
	}
	bindingID, err := newID()
	if err != nil {
		return domain.Workspace{}, err
	}
	candidate.Chains = append(candidate.Chains, domain.Chain{ID: chainID, Name: input.Name, HopNodeIDs: append([]string(nil), input.HopNodeIDs...)})
	candidate.PortBindings = append(candidate.PortBindings, domain.PortBinding{ID: bindingID, ChainID: chainID, ListenHost: "127.0.0.1", ListenPort: port})
	return s.commit(candidate)
}

func (s *WorkspaceService) UpdateChain(input UpdateChainInput) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	var chain *domain.Chain
	for i := range candidate.Chains {
		if candidate.Chains[i].ID == input.ID {
			chain = &candidate.Chains[i]
			break
		}
	}
	if chain == nil {
		return domain.Workspace{}, fmt.Errorf("Chain %q does not exist", input.ID)
	}
	chain.Name, chain.HopNodeIDs = input.Name, append([]string(nil), input.HopNodeIDs...)
	port := input.ListenPort
	found := false
	for _, binding := range candidate.PortBindings {
		if binding.ChainID == input.ID {
			if port == 0 {
				port = binding.ListenPort
			}
			found = true
			break
		}
	}
	if port == 0 {
		port = nextAvailablePortExcluding(candidate, input.ID)
	}
	if port == 0 {
		return domain.Workspace{}, errors.New("no available local ports remain")
	}
	for i := range candidate.PortBindings {
		if candidate.PortBindings[i].ChainID == input.ID {
			candidate.PortBindings[i].ListenPort = port
			break
		}
	}
	if !found {
		bindingID, err := newID()
		if err != nil {
			return domain.Workspace{}, err
		}
		candidate.PortBindings = append(candidate.PortBindings, domain.PortBinding{ID: bindingID, ChainID: input.ID, ListenHost: "127.0.0.1", ListenPort: port})
	}
	return s.commit(candidate)
}

func (s *WorkspaceService) DeleteChain(chainID string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	chains := candidate.Chains[:0]
	for _, chain := range candidate.Chains {
		if chain.ID != chainID {
			chains = append(chains, chain)
		}
	}
	if len(chains) == len(candidate.Chains) {
		return domain.Workspace{}, fmt.Errorf("Chain %q does not exist", chainID)
	}
	candidate.Chains = chains
	bindings := candidate.PortBindings[:0]
	for _, binding := range candidate.PortBindings {
		if binding.ChainID != chainID {
			bindings = append(bindings, binding)
		}
	}
	candidate.PortBindings = bindings
	if candidate.TUN.Kind == domain.TUNBindingChain && candidate.TUN.TargetID == chainID {
		candidate.TUN = domain.TUNBinding{Kind: domain.TUNBindingNone}
	}
	return s.commit(candidate)
}

func (s *WorkspaceService) SetActiveBaseNode(nodeID string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	if nodeID != "" && !hasNode(candidate, nodeID) {
		return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", nodeID)
	}
	candidate.ActiveNodeID = nodeID
	return s.commit(candidate)
}

func (s *WorkspaceService) BindTUNToBaseNode(nodeID string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	if !hasNode(candidate, nodeID) {
		return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", nodeID)
	}
	candidate.TUN = domain.TUNBinding{Kind: domain.TUNBindingNode, TargetID: nodeID}
	candidate.TUN.Enabled = true
	return s.commit(candidate)
}

func (s *WorkspaceService) BindTUNToChain(chainID string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	if !hasChain(candidate, chainID) {
		return domain.Workspace{}, fmt.Errorf("Chain %q does not exist", chainID)
	}
	candidate.TUN = domain.TUNBinding{Kind: domain.TUNBindingChain, TargetID: chainID}
	candidate.TUN.Enabled = true
	return s.commit(candidate)
}

func (s *WorkspaceService) ClearTUNBinding() (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	candidate.TUN = domain.TUNBinding{Kind: domain.TUNBindingNone}
	return s.commit(candidate)
}

func (s *WorkspaceService) SetTUNEnabled(enabled bool) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	if enabled && candidate.TUN.Kind == domain.TUNBindingNone {
		return domain.Workspace{}, errors.New("bind TUN to a Base Node or complete Chain before enabling it")
	}
	candidate.TUN.Enabled = enabled
	return s.commit(candidate)
}

func (s *WorkspaceService) commit(candidate domain.Workspace) (domain.Workspace, error) {
	if err := candidate.Validate(); err != nil {
		return domain.Workspace{}, err
	}
	if s.store != nil {
		if err := s.store.Save(context.Background(), candidate); err != nil {
			return domain.Workspace{}, err
		}
	}
	s.state = candidate
	return cloneWorkspace(candidate), nil
}

func cloneWorkspace(workspace domain.Workspace) domain.Workspace {
	data, _ := json.Marshal(workspace)
	var clone domain.Workspace
	_ = json.Unmarshal(data, &clone)
	return clone
}

func hasNode(workspace domain.Workspace, id string) bool {
	for _, node := range workspace.Nodes {
		if node.ID == id {
			return true
		}
	}
	return false
}
func hasChain(workspace domain.Workspace, id string) bool {
	for _, chain := range workspace.Chains {
		if chain.ID == id {
			return true
		}
	}
	return false
}

func nextAvailablePort(workspace domain.Workspace) uint16 {
	return nextAvailablePortExcluding(workspace, "")
}

func nextAvailablePortExcluding(workspace domain.Workspace, chainID string) uint16 {
	used := map[uint16]bool{workspace.Settings.BaseListenPort: true}
	for _, binding := range workspace.PortBindings {
		if binding.ChainID != chainID {
			used[binding.ListenPort] = true
		}
	}
	for port := uint32(20001); port <= 65535; port++ {
		if !used[uint16(port)] {
			return uint16(port)
		}
	}
	return 0
}

func newID() (string, error) {
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes[:]), nil
}
