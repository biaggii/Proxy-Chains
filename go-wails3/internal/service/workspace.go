package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/autostart"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/core"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/migration"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/profiles"
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
	selectExecutable        func(string) (string, error)
	selectDirectory         func() (string, error)
	selectOpenFile          func(string) (string, error)
	selectSaveFile          func(string) (string, error)
	supervisor              *runtimecore.Supervisor
	configDir               string
	activeConfigPath        string
	schedulerStarted        bool
	refreshingSubscriptions map[string]*subscriptionRefreshCall
}

type profileWorkspaceStore interface {
	WorkspaceStore
	State() profiles.State
	Create(string) (profiles.Profile, error)
	Rename(string, string) error
	Delete(string) error
	Switch(string) (domain.Workspace, error)
	LoadProfile(string) (domain.Workspace, error)
	MoveDataLocation(string) error
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
	Insecure bool            `json:"insecure,omitempty"`
	ALPN     []string        `json:"alpn,omitempty"`
	SNI      string          `json:"sni,omitempty"`
	Network  string          `json:"network,omitempty"`
	Path     string          `json:"path,omitempty"`
	Host     string          `json:"host,omitempty"`
	GroupID  string          `json:"groupId,omitempty"`
}

type UpdateNodeInput struct {
	ID       string           `json:"id"`
	Name     string           `json:"name"`
	Server   string           `json:"server"`
	Port     uint16           `json:"port"`
	Network  string           `json:"network"`
	Path     string           `json:"path,omitempty"`
	Host     string           `json:"host,omitempty"`
	TLS      bool             `json:"tls"`
	SNI      string           `json:"sni,omitempty"`
	Protocol *domain.Protocol `json:"protocol,omitempty"`
	Insecure bool             `json:"insecure,omitempty"`
	ALPN     []string         `json:"alpn,omitempty"`
	Username *string          `json:"username,omitempty"`
	Password *string          `json:"password,omitempty"`
	GroupID  *string          `json:"groupId,omitempty"`
}

type NodeCredentials struct {
	Username string `json:"username,omitempty"`
	Password string `json:"password,omitempty"`
}

func NewWorkspaceService() *WorkspaceService {
	return &WorkspaceService{state: domain.DefaultWorkspace()}
}

func NewWorkspaceServiceWithStore(ctx context.Context, store WorkspaceStore) (*WorkspaceService, error) {
	return NewWorkspaceServiceWithDependencies(ctx, store, nil, nil, nil)
}

func NewWorkspaceServiceWithDependencies(ctx context.Context, store WorkspaceStore, secrets security.SecretStore, selectFile func() (string, error), onRuntimeEvent func(runtimecore.Event)) (*WorkspaceService, error) {
	return NewWorkspaceServiceWithPickers(ctx, store, secrets, selectFile, nil, onRuntimeEvent)
}

func NewWorkspaceServiceWithPickers(ctx context.Context, store WorkspaceStore, secrets security.SecretStore, selectFile func() (string, error), selectExecutable func(string) (string, error), onRuntimeEvent func(runtimecore.Event)) (*WorkspaceService, error) {
	state, err := store.Load(ctx)
	if err != nil {
		return nil, err
	}
	if err := state.Validate(); err != nil {
		return nil, err
	}
	configDir := state.Settings.ConfigOutputDir
	if configDir == "" {
		if manager, ok := store.(interface{ State() profiles.State }); ok {
			configDir = filepath.Join(manager.State().DataLocation, "runtime")
		}
	}
	if configDir == "" {
		base, err := os.UserConfigDir()
		if err != nil {
			return nil, err
		}
		configDir = filepath.Join(base, "ChainPort Gateway", "runtime")
	}
	return &WorkspaceService{appContext: ctx, store: store, state: state, secrets: secrets, selectLegacyFile: selectFile, selectExecutable: selectExecutable, supervisor: runtimecore.NewSupervisor(onRuntimeEvent), configDir: configDir, refreshingSubscriptions: map[string]*subscriptionRefreshCall{}}, nil
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

func ConfigureFileDialogs(s *WorkspaceService, selectDirectory func() (string, error), selectOpenFile func(string) (string, error), selectSaveFile func(string) (string, error)) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.selectDirectory = selectDirectory
	s.selectOpenFile = selectOpenFile
	s.selectSaveFile = selectSaveFile
}

func (s *WorkspaceService) GetProfileState() profiles.State {
	s.mu.RLock()
	manager, _ := s.store.(profileWorkspaceStore)
	s.mu.RUnlock()
	if manager == nil {
		return profiles.State{}
	}
	return manager.State()
}

func (s *WorkspaceService) CreateProfile(name string) (profiles.State, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	manager, ok := s.store.(profileWorkspaceStore)
	if !ok {
		return profiles.State{}, errors.New("profile manager is unavailable")
	}
	if len(s.refreshingSubscriptions) > 0 {
		return profiles.State{}, errors.New("wait for subscription refreshes to finish before managing profiles")
	}
	if _, err := manager.Create(name); err != nil {
		return profiles.State{}, err
	}
	return manager.State(), nil
}

func (s *WorkspaceService) RenameProfile(id, name string) (profiles.State, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	manager, ok := s.store.(profileWorkspaceStore)
	if !ok {
		return profiles.State{}, errors.New("profile manager is unavailable")
	}
	if err := manager.Rename(id, name); err != nil {
		return profiles.State{}, err
	}
	return manager.State(), nil
}

func (s *WorkspaceService) DeleteProfile(id string) (profiles.State, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	manager, ok := s.store.(profileWorkspaceStore)
	if !ok {
		return profiles.State{}, errors.New("profile manager is unavailable")
	}
	if len(s.refreshingSubscriptions) > 0 {
		return profiles.State{}, errors.New("wait for subscription refreshes to finish before managing profiles")
	}
	workspace, err := manager.LoadProfile(id)
	if err != nil {
		return profiles.State{}, err
	}
	if err := manager.Delete(id); err != nil {
		return profiles.State{}, err
	}
	if s.secrets != nil && s.secrets.Available() {
		for _, reference := range workspaceSecretReferences(workspace) {
			if err := s.secrets.Delete(s.appContext, reference); err != nil {
				return manager.State(), fmt.Errorf("profile deleted, but credential cleanup failed for %q: %w", reference, err)
			}
		}
	}
	return manager.State(), nil
}

func (s *WorkspaceService) SwitchProfile(id string) (domain.Workspace, profiles.State, error) {
	s.mu.RLock()
	manager, ok := s.store.(profileWorkspaceStore)
	refreshing := len(s.refreshingSubscriptions) > 0
	s.mu.RUnlock()
	if !ok {
		return domain.Workspace{}, profiles.State{}, errors.New("profile manager is unavailable")
	}
	if refreshing {
		return domain.Workspace{}, profiles.State{}, errors.New("wait for subscription refreshes to finish before switching profiles")
	}
	if id == manager.State().ActiveProfileID {
		return s.GetWorkspace(), manager.State(), nil
	}
	if err := s.StopCore(); err != nil {
		return domain.Workspace{}, profiles.State{}, fmt.Errorf("stop the core before switching profiles: %w", err)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.refreshingSubscriptions) > 0 {
		return domain.Workspace{}, profiles.State{}, errors.New("wait for subscription refreshes to finish before switching profiles")
	}
	previousProfileID := manager.State().ActiveProfileID
	previousStartup := s.state.Settings.RunOnStartup
	workspace, err := manager.Switch(id)
	if err != nil {
		return domain.Workspace{}, profiles.State{}, err
	}
	if workspace.Settings.RunOnStartup != previousStartup {
		if err := autostart.SetEnabled(workspace.Settings.RunOnStartup); err != nil {
			rollbackWorkspace, rollbackErr := manager.Switch(previousProfileID)
			if rollbackErr == nil {
				s.state = rollbackWorkspace
				_ = autostart.SetEnabled(previousStartup)
			}
			if rollbackErr != nil {
				return domain.Workspace{}, profiles.State{}, fmt.Errorf("update startup registration: %v; profile rollback failed: %w", err, rollbackErr)
			}
			return domain.Workspace{}, profiles.State{}, fmt.Errorf("update system startup registration: %w", err)
		}
	}
	s.state = workspace
	s.configDir = profileRuntimeDir(manager.State().DataLocation, workspace.Settings)
	return cloneWorkspace(workspace), manager.State(), nil
}

func (s *WorkspaceService) PickDataLocation() (string, error) {
	s.mu.RLock()
	picker := s.selectDirectory
	s.mu.RUnlock()
	if picker == nil {
		return "", errors.New("directory picker is unavailable")
	}
	return picker()
}

func (s *WorkspaceService) MoveDataLocation(path string) (profiles.State, error) {
	if err := s.StopCore(); err != nil {
		return profiles.State{}, fmt.Errorf("stop the core before moving data: %w", err)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	manager, ok := s.store.(profileWorkspaceStore)
	if !ok {
		return profiles.State{}, errors.New("profile manager is unavailable")
	}
	if len(s.refreshingSubscriptions) > 0 {
		return profiles.State{}, errors.New("wait for subscription refreshes to finish before moving data")
	}
	if err := manager.MoveDataLocation(path); err != nil {
		return profiles.State{}, err
	}
	state := manager.State()
	s.configDir = profileRuntimeDir(state.DataLocation, s.state.Settings)
	return state, nil
}

func profileRuntimeDir(root string, settings domain.Settings) string {
	if strings.TrimSpace(settings.ConfigOutputDir) != "" {
		return settings.ConfigOutputDir
	}
	return filepath.Join(root, "runtime")
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
	if s.supervisor != nil && s.supervisor.Snapshot().Status == runtimecore.StatusRunning && (settings.BaseListenHost != s.state.Settings.BaseListenHost || settings.BaseListenPort != s.state.Settings.BaseListenPort) {
		return domain.Workspace{}, errors.New("stop the running core before changing the mixed listener host or port")
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

// PickCoreExecutable opens the platform file picker and returns a validated path for the Settings draft.
func (s *WorkspaceService) PickCoreExecutable(coreName string) (string, error) {
	s.mu.RLock()
	picker := s.selectExecutable
	s.mu.RUnlock()
	if picker == nil {
		return "", errors.New("core executable file picker is unavailable")
	}
	coreName = strings.ToLower(strings.TrimSpace(coreName))
	if coreName != "sing-box" && coreName != "xray" && coreName != "mihomo" {
		return "", fmt.Errorf("unsupported core %q", coreName)
	}
	path, err := picker(coreName)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(path) == "" {
		return "", nil
	}
	info, err := os.Stat(path)
	if err != nil {
		return "", fmt.Errorf("inspect selected executable: %w", err)
	}
	if !info.Mode().IsRegular() {
		return "", errors.New("selected core executable must be a file")
	}
	if runtime.GOOS != "windows" && info.Mode().Perm()&0o111 == 0 {
		return "", errors.New("selected core file is not executable; grant execute permission first")
	}
	return path, nil
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
		return domain.Workspace{}, errors.New("manual node creation currently supports SOCKS5, HTTP and HTTPS (HTTP with TLS)")
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
		Transport:   domain.Transport{Network: network, Path: input.Path, Host: input.Host}, TLS: domain.TLSOptions{Enabled: input.TLS, Insecure: input.Insecure, SNI: input.SNI, ALPN: append([]string(nil), input.ALPN...)},
		GroupID: input.GroupID,
	})
	result, err := s.commit(candidate)
	if err != nil && s.secrets != nil {
		for _, ref := range refs {
			_ = s.secrets.Delete(context.Background(), ref)
		}
	}
	return result, err
}

// GetNodeCredentials reads only the username/password fields requested by the node editor.
// Secret values are never included in Workspace snapshots or persisted in SQLite.
func (s *WorkspaceService) GetNodeCredentials(nodeID string) (NodeCredentials, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, node := range s.state.Nodes {
		if node.ID != nodeID {
			continue
		}
		credentials := NodeCredentials{}
		if node.Credentials.UsernameRef == "" && node.Credentials.PasswordRef == "" {
			return credentials, nil
		}
		if s.secrets == nil || !s.secrets.Available() {
			return credentials, security.ErrUnavailable
		}
		var err error
		if node.Credentials.UsernameRef != "" {
			credentials.Username, err = s.secrets.Get(context.Background(), node.Credentials.UsernameRef)
			if err != nil {
				return NodeCredentials{}, fmt.Errorf("read stored username: %w", err)
			}
		}
		if node.Credentials.PasswordRef != "" {
			credentials.Password, err = s.secrets.Get(context.Background(), node.Credentials.PasswordRef)
			if err != nil {
				return NodeCredentials{}, fmt.Errorf("read stored password: %w", err)
			}
		}
		return credentials, nil
	}
	return NodeCredentials{}, fmt.Errorf("Base Node %q does not exist", nodeID)
}

// UpdateNode edits public metadata and optionally replaces username/password vault entries.
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
		if input.Protocol != nil {
			if *input.Protocol != domain.ProtocolSOCKS5 && *input.Protocol != domain.ProtocolHTTP {
				return domain.Workspace{}, errors.New("manual node editing supports SOCKS5, HTTP and HTTPS (HTTP with TLS)")
			}
			node.Protocol = *input.Protocol
		}
		if input.Network != "" {
			node.Transport.Network = input.Network
		}
		node.Transport.Path = input.Path
		node.Transport.Host = input.Host
		node.TLS.Enabled = input.TLS
		node.TLS.Insecure = input.Insecure
		node.TLS.SNI = input.SNI
		node.TLS.ALPN = append([]string(nil), input.ALPN...)
		if input.GroupID != nil {
			node.GroupID = *input.GroupID
		}
		newRefs := []string{}
		oldRefs := []string{}
		replace := func(value *string, currentRef string) (string, error) {
			if value == nil {
				return currentRef, nil
			}
			if currentRef != "" {
				if s.secrets == nil || !s.secrets.Available() {
					return "", security.ErrUnavailable
				}
				current, err := s.secrets.Get(context.Background(), currentRef)
				if err != nil {
					return "", fmt.Errorf("read existing credential before update: %w", err)
				}
				if current == *value {
					return currentRef, nil
				}
			}
			if *value == "" {
				if currentRef != "" {
					oldRefs = append(oldRefs, currentRef)
				}
				return "", nil
			}
			if s.secrets == nil || !s.secrets.Available() {
				return "", security.ErrUnavailable
			}
			ref, err := newID()
			if err != nil {
				return "", err
			}
			if err := s.secrets.Put(context.Background(), ref, *value); err != nil {
				return "", err
			}
			newRefs = append(newRefs, ref)
			if currentRef != "" {
				oldRefs = append(oldRefs, currentRef)
			}
			return ref, nil
		}
		usernameRef, err := replace(input.Username, node.Credentials.UsernameRef)
		if err != nil {
			return domain.Workspace{}, err
		}
		passwordRef, err := replace(input.Password, node.Credentials.PasswordRef)
		if err != nil {
			for _, ref := range newRefs {
				_ = s.secrets.Delete(context.Background(), ref)
			}
			return domain.Workspace{}, err
		}
		node.Credentials.UsernameRef, node.Credentials.PasswordRef = usernameRef, passwordRef
		result, err := s.commit(candidate)
		if err != nil {
			for _, ref := range newRefs {
				_ = s.secrets.Delete(context.Background(), ref)
			}
			return domain.Workspace{}, err
		}
		for _, ref := range oldRefs {
			_ = s.secrets.Delete(context.Background(), ref)
		}
		return result, nil
	}
	return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", input.ID)
}

func (s *WorkspaceService) CreateNodeGroup(name string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	name = strings.TrimSpace(name)
	if name == "" {
		return domain.Workspace{}, errors.New("group name is required")
	}
	candidate := cloneWorkspace(s.state)
	for _, group := range candidate.Groups {
		if strings.EqualFold(group.Name, name) {
			return domain.Workspace{}, fmt.Errorf("group %q already exists", name)
		}
	}
	if customName := strings.TrimSpace(candidate.Settings.CustomNodesGroupName); customName != "" && strings.EqualFold(customName, name) {
		return domain.Workspace{}, fmt.Errorf("group %q already exists", name)
	}
	id, err := newID()
	if err != nil {
		return domain.Workspace{}, err
	}
	candidate.Groups = append(candidate.Groups, domain.NodeGroup{ID: id, Name: name})
	return s.commit(candidate)
}

func (s *WorkspaceService) RenameNodeGroup(id, name string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	name = strings.TrimSpace(name)
	if name == "" {
		return domain.Workspace{}, errors.New("group name is required")
	}
	candidate := cloneWorkspace(s.state)
	for i := range candidate.Groups {
		if candidate.Groups[i].ID != id && strings.EqualFold(candidate.Groups[i].Name, name) {
			return domain.Workspace{}, fmt.Errorf("group %q already exists", name)
		}
	}
	if customName := strings.TrimSpace(candidate.Settings.CustomNodesGroupName); customName != "" && strings.EqualFold(customName, name) {
		return domain.Workspace{}, fmt.Errorf("group %q already exists", name)
	}
	for i := range candidate.Groups {
		if candidate.Groups[i].ID == id {
			candidate.Groups[i].Name = name
			return s.commit(candidate)
		}
	}
	return domain.Workspace{}, fmt.Errorf("group %q does not exist", id)
}

func (s *WorkspaceService) DeleteNodeGroup(id string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	found := false
	groups := candidate.Groups[:0]
	for _, group := range candidate.Groups {
		if group.ID == id {
			found = true
			continue
		}
		groups = append(groups, group)
	}
	if !found {
		return domain.Workspace{}, fmt.Errorf("group %q does not exist", id)
	}
	candidate.Groups = groups
	for i := range candidate.Nodes {
		if candidate.Nodes[i].GroupID == id {
			candidate.Nodes[i].GroupID = ""
		}
	}
	return s.commit(candidate)
}

func (s *WorkspaceService) RenameCustomNodesGroup(name string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	name = strings.TrimSpace(name)
	if name == "" {
		return domain.Workspace{}, errors.New("custom group name is required")
	}
	candidate := cloneWorkspace(s.state)
	for _, group := range candidate.Groups {
		if strings.EqualFold(group.Name, name) {
			return domain.Workspace{}, fmt.Errorf("group %q already exists", name)
		}
	}
	for _, subscription := range candidate.Subscriptions {
		if strings.EqualFold(subscription.Name, name) {
			return domain.Workspace{}, fmt.Errorf("subscription group %q already exists", name)
		}
	}
	candidate.Settings.CustomNodesGroupName = name
	return s.commit(candidate)
}

// MoveNodeToGroup moves a node out of its previous group. Moving an imported
// subscription node detaches it from the feed so refresh/delete operations no
// longer overwrite or remove the user's manually moved node.
func (s *WorkspaceService) MoveNodeToGroup(nodeID, groupID string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	if groupID != "" && !hasNodeGroup(candidate, groupID) {
		return domain.Workspace{}, fmt.Errorf("destination group %q does not exist", groupID)
	}
	for i := range candidate.Nodes {
		if candidate.Nodes[i].ID == nodeID {
			candidate.Nodes[i].GroupID = groupID
			if candidate.Nodes[i].SourceID != "" {
				candidate.Nodes[i].SourceID = ""
				candidate.Nodes[i].Tags = appendUnique(candidate.Nodes[i].Tags, "detached-subscription")
			}
			return s.commit(candidate)
		}
	}
	return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", nodeID)
}

// CopyNodeToGroup creates an independent, manually managed copy of a node.
// Every credential-vault reference is duplicated; the copy is not owned by its
// original subscription and will not be replaced on the next subscription refresh.
func (s *WorkspaceService) CopyNodeToGroup(nodeID, groupID string) (domain.Workspace, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	if groupID != "" && !hasNodeGroup(candidate, groupID) {
		return domain.Workspace{}, fmt.Errorf("destination group %q does not exist", groupID)
	}
	var source *domain.Node
	for i := range candidate.Nodes {
		if candidate.Nodes[i].ID == nodeID {
			source = &candidate.Nodes[i]
			break
		}
	}
	if source == nil {
		return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", nodeID)
	}
	copyNode := *source
	newNodeID, err := newID()
	if err != nil {
		return domain.Workspace{}, err
	}
	copyNode.ID = newNodeID
	copyNode.Name = uniqueCopyName(candidate.Nodes, source.Name)
	copyNode.SourceID = ""
	copyNode.GroupID = groupID
	copyNode.Tags = append([]string(nil), source.Tags...)
	copyNode.Tags = removeTags(copyNode.Tags, "stale-subscription-node", "detached-subscription")
	copyNode.ALPN = append([]string(nil), source.ALPN...)
	copyNode.TLS.ALPN = append([]string(nil), source.TLS.ALPN...)
	copyNode.Options = cloneStringMap(source.Options)
	newRefs := []string{}
	copyRef := func(reference string) (string, error) {
		if reference == "" {
			return "", nil
		}
		if s.secrets == nil || !s.secrets.Available() {
			return "", security.ErrUnavailable
		}
		value, err := s.secrets.Get(context.Background(), reference)
		if err != nil {
			return "", fmt.Errorf("read source node secret: %w", err)
		}
		newRef, err := newID()
		if err != nil {
			return "", err
		}
		if err := s.secrets.Put(context.Background(), newRef, value); err != nil {
			return "", err
		}
		newRefs = append(newRefs, newRef)
		return newRef, nil
	}
	refs := []*string{&copyNode.Credentials.UsernameRef, &copyNode.Credentials.PasswordRef, &copyNode.Credentials.UUIDRef, &copyNode.Credentials.PrivateKeyRef, &copyNode.SourceMetadataRef}
	originalRefs := []string{source.Credentials.UsernameRef, source.Credentials.PasswordRef, source.Credentials.UUIDRef, source.Credentials.PrivateKeyRef, source.SourceMetadataRef}
	for i, ref := range originalRefs {
		clonedRef, err := copyRef(ref)
		if err != nil {
			for _, created := range newRefs {
				_ = s.secrets.Delete(context.Background(), created)
			}
			return domain.Workspace{}, err
		}
		*refs[i] = clonedRef
	}
	candidate.Nodes = append(candidate.Nodes, copyNode)
	result, err := s.commit(candidate)
	if err != nil {
		for _, created := range newRefs {
			_ = s.secrets.Delete(context.Background(), created)
		}
	}
	return result, err
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
	if nodeID != "" {
		s.mu.RLock()
		var selected *domain.Node
		for i := range s.state.Nodes {
			if s.state.Nodes[i].ID == nodeID {
				node := s.state.Nodes[i]
				selected = &node
				break
			}
		}
		s.mu.RUnlock()
		if selected == nil {
			return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", nodeID)
		}
		if selected.Protocol != domain.ProtocolWireGuard && strings.ToLower(selected.Transport.Network) != "udp" {
			address := net.JoinHostPort(strings.TrimSpace(selected.Server), fmt.Sprintf("%d", selected.Port))
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			connection, err := (&net.Dialer{}).DialContext(ctx, "tcp", address)
			if err != nil {
				return domain.Workspace{}, fmt.Errorf("cannot activate %q: proxy endpoint %s is not reachable: %w", selected.Name, address, err)
			}
			_ = connection.Close()
		}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	candidate := cloneWorkspace(s.state)
	if nodeID != "" && !hasNode(candidate, nodeID) {
		return domain.Workspace{}, fmt.Errorf("Base Node %q does not exist", nodeID)
	}
	candidate.ActiveNodeID = nodeID
	return s.commit(candidate)
}

func hasNodeGroup(workspace domain.Workspace, id string) bool {
	for _, group := range workspace.Groups {
		if group.ID == id {
			return true
		}
	}
	return false
}

func uniqueCopyName(nodes []domain.Node, name string) string {
	base := name + " (copy)"
	candidate := base
	for suffix := 2; ; suffix++ {
		used := false
		for _, node := range nodes {
			if strings.EqualFold(node.Name, candidate) {
				used = true
				break
			}
		}
		if !used {
			return candidate
		}
		candidate = fmt.Sprintf("%s %d", base, suffix)
	}
}

func removeTags(tags []string, remove ...string) []string {
	filtered := tags[:0]
	for _, tag := range tags {
		keep := true
		for _, item := range remove {
			if tag == item {
				keep = false
				break
			}
		}
		if keep {
			filtered = append(filtered, tag)
		}
	}
	return filtered
}

func cloneStringMap(values map[string]string) map[string]string {
	if values == nil {
		return nil
	}
	cloned := make(map[string]string, len(values))
	for key, value := range values {
		cloned[key] = value
	}
	return cloned
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
