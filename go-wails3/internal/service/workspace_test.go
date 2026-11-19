package service

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
)

type memoryStore struct{ workspace domain.Workspace }

func (m *memoryStore) Load(context.Context) (domain.Workspace, error) {
	return cloneWorkspace(m.workspace), nil
}
func (m *memoryStore) Save(_ context.Context, workspace domain.Workspace) error {
	m.workspace = cloneWorkspace(workspace)
	return nil
}

func TestChainCRUDAndWholeChainTUN(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "entry", Name: "Entry", Protocol: domain.ProtocolVLESS, Server: "entry.example", Port: 443}, {ID: "exit", Name: "Exit", Protocol: domain.ProtocolSOCKS5, Server: "exit.example", Port: 1080}}
	store := &memoryStore{workspace: w}
	service, err := NewWorkspaceServiceWithStore(context.Background(), store)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateChain(CreateChainInput{Name: "Route", HopNodeIDs: []string{"entry", "exit"}, ListenPort: 23001})
	if err != nil {
		t.Fatal(err)
	}
	if len(created.Chains) != 1 || created.PortBindings[0].ListenPort != 23001 {
		t.Fatalf("unexpected created Chain: %+v", created)
	}
	chainID := created.Chains[0].ID
	updated, err := service.UpdateChain(UpdateChainInput{ID: chainID, Name: "Updated", HopNodeIDs: []string{"entry", "exit"}, ListenPort: 23002})
	if err != nil {
		t.Fatal(err)
	}
	if updated.PortBindings[0].ListenPort != 23002 || updated.Chains[0].HopNodeIDs[1] != "exit" {
		t.Fatalf("unexpected updated Chain: %+v", updated)
	}
	bound, err := service.BindTUNToChain(chainID)
	if err != nil {
		t.Fatal(err)
	}
	if bound.TUN.Kind != domain.TUNBindingChain || bound.TUN.TargetID != chainID || !bound.TUN.Enabled {
		t.Fatalf("TUN did not bind the whole Chain: %+v", bound.TUN)
	}
	deleted, err := service.DeleteChain(chainID)
	if err != nil {
		t.Fatal(err)
	}
	if len(deleted.Chains) != 0 || len(deleted.PortBindings) != 0 || deleted.TUN.Kind != domain.TUNBindingNone {
		t.Fatalf("Chain cleanup failed: %+v", deleted)
	}
}

func TestCreateNodePersistsWithoutPlaintextCredentials(t *testing.T) {
	store := &memoryStore{workspace: domain.DefaultWorkspace()}
	service, err := NewWorkspaceServiceWithStore(context.Background(), store)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateNode(CreateNodeInput{Name: "Local SOCKS", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080})
	if err != nil {
		t.Fatal(err)
	}
	if len(created.Nodes) != 1 || created.Nodes[0].Credentials.PasswordRef != "" {
		t.Fatalf("unexpected node create result: %+v", created.Nodes)
	}
}

func TestCreateHTTPSNodeStoresHTTPProtocolWithTLS(t *testing.T) {
	store := &memoryStore{workspace: domain.DefaultWorkspace()}
	service, err := NewWorkspaceServiceWithStore(context.Background(), store)
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateNode(CreateNodeInput{Name: "HTTPS proxy", Protocol: domain.ProtocolHTTP, Server: "proxy.example", Port: 8443, TLS: true, SNI: "proxy.example", Insecure: false, ALPN: []string{"h2", "http/1.1"}})
	if err != nil {
		t.Fatal(err)
	}
	node := created.Nodes[0]
	if node.Protocol != domain.ProtocolHTTP || !node.TLS.Enabled || node.TLS.SNI != "proxy.example" || len(node.TLS.ALPN) != 2 || node.TLS.ALPN[0] != "h2" {
		t.Fatalf("HTTPS proxy was not persisted as HTTP with TLS: %+v", node)
	}
}

func TestUpdateManualNodeCanSwitchHTTPAndHTTPS(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "node", Name: "Proxy", Protocol: domain.ProtocolHTTP, Server: "proxy.example", Port: 8080, Transport: domain.Transport{Network: "tcp"}}}
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	httpsProtocol := domain.ProtocolHTTP
	updated, err := service.UpdateNode(UpdateNodeInput{ID: "node", Name: "Proxy", Server: "proxy.example", Port: 8443, Network: "tcp", Protocol: &httpsProtocol, TLS: true, SNI: "proxy.example", Insecure: true, ALPN: []string{"h2"}})
	if err != nil {
		t.Fatal(err)
	}
	node := updated.Nodes[0]
	if node.Protocol != domain.ProtocolHTTP || !node.TLS.Enabled || !node.TLS.Insecure || node.TLS.SNI != "proxy.example" || len(node.TLS.ALPN) != 1 || node.TLS.ALPN[0] != "h2" {
		t.Fatalf("HTTPS node update was not saved: %+v", node)
	}
	plainProtocol := domain.ProtocolSOCKS5
	updated, err = service.UpdateNode(UpdateNodeInput{ID: "node", Name: "Proxy", Server: "proxy.example", Port: 1080, Network: "tcp", Protocol: &plainProtocol, TLS: false})
	if err != nil {
		t.Fatal(err)
	}
	if updated.Nodes[0].Protocol != domain.ProtocolSOCKS5 || updated.Nodes[0].TLS.Enabled {
		t.Fatalf("node protocol was not switched to SOCKS5: %+v", updated.Nodes[0])
	}
}

func TestUpdateNodeEditsMetadataWithoutExposingOrReplacingVaultCredentials(t *testing.T) {
	secrets := subscriptionSecrets{"node-password": "kept-secret"}
	w := domain.DefaultWorkspace()
	w.Groups = []domain.NodeGroup{{ID: "group-1", Name: "Work"}}
	w.Nodes = []domain.Node{{ID: "node-1", Name: "Old", Protocol: domain.ProtocolVLESS, Server: "old.example", Port: 443, GroupID: "group-1", Credentials: domain.Credentials{PasswordRef: "node-password"}, Transport: domain.Transport{Network: "tcp"}}}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: w}, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	updated, err := service.UpdateNode(UpdateNodeInput{ID: "node-1", Name: "Renamed", Server: "new.example", Port: 8443, Network: "ws", Path: "/proxy", Host: "cdn.example", TLS: true, SNI: "cdn.example"})
	if err != nil {
		t.Fatal(err)
	}
	node := updated.Nodes[0]
	if node.Name != "Renamed" || node.Server != "new.example" || node.Port != 8443 || node.Protocol != domain.ProtocolVLESS || node.GroupID != "group-1" || node.Credentials.PasswordRef != "node-password" || node.Transport.Network != "ws" || node.Transport.Path != "/proxy" || !node.TLS.Enabled || node.TLS.SNI != "cdn.example" {
		t.Fatalf("node metadata update lost or changed protected fields: %+v", node)
	}
	if secrets["node-password"] != "kept-secret" {
		t.Fatal("updating node metadata changed its vault credential")
	}
}

func TestNodeEditorCanReadAndReplaceSOCKSCredentialsInVault(t *testing.T) {
	secrets := subscriptionSecrets{"node-user": "old-user", "node-password": "old-password"}
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "node-1", Name: "SOCKS", Protocol: domain.ProtocolSOCKS5, Server: "proxy.example", Port: 1080, Credentials: domain.Credentials{UsernameRef: "node-user", PasswordRef: "node-password"}}}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: w}, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	credentials, err := service.GetNodeCredentials("node-1")
	if err != nil {
		t.Fatal(err)
	}
	if credentials.Username != "old-user" || credentials.Password != "old-password" {
		t.Fatalf("editor did not receive saved credentials: %+v", credentials)
	}
	username, password := "new-user", "new-password"
	updated, err := service.UpdateNode(UpdateNodeInput{ID: "node-1", Name: "SOCKS", Server: "proxy.example", Port: 1080, Network: "tcp", Username: &username, Password: &password})
	if err != nil {
		t.Fatal(err)
	}
	node := updated.Nodes[0]
	if node.Credentials.UsernameRef == "node-user" || node.Credentials.PasswordRef == "node-password" {
		t.Fatal("updated credentials did not receive new vault references")
	}
	if secrets[node.Credentials.UsernameRef] != username || secrets[node.Credentials.PasswordRef] != password {
		t.Fatal("new credential values were not stored in the vault")
	}
	if _, ok := secrets["node-user"]; ok {
		t.Fatal("replaced username secret was not deleted")
	}
	if _, ok := secrets["node-password"]; ok {
		t.Fatal("replaced password secret was not deleted")
	}
}

func TestNodeGroupCRUDAndAssignment(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "node-1", Name: "Node", Protocol: domain.ProtocolSOCKS5, Server: "localhost", Port: 1080}}
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	created, err := service.CreateNodeGroup("Work")
	if err != nil {
		t.Fatal(err)
	}
	groupID := created.Groups[0].ID
	if _, err := service.CreateNodeGroup("work"); err == nil {
		t.Fatal("expected case-insensitive duplicate group rejection")
	}
	updated, err := service.UpdateNode(UpdateNodeInput{ID: "node-1", Name: "Node", Server: "localhost", Port: 1080, Network: "tcp", GroupID: &groupID})
	if err != nil {
		t.Fatal(err)
	}
	if updated.Nodes[0].GroupID != groupID {
		t.Fatal("node was not assigned to the new group")
	}
	renamed, err := service.RenameNodeGroup(groupID, "Work Nodes")
	if err != nil || renamed.Groups[0].Name != "Work Nodes" {
		t.Fatalf("group rename failed: %+v %v", renamed, err)
	}
	deleted, err := service.DeleteNodeGroup(groupID)
	if err != nil {
		t.Fatal(err)
	}
	if len(deleted.Groups) != 0 || deleted.Nodes[0].GroupID != "" {
		t.Fatalf("group deletion did not clear node assignments: %+v", deleted)
	}
}

func TestPickCoreExecutableUsesNativePickerAndPersistsSelection(t *testing.T) {
	w := domain.DefaultWorkspace()
	executable := filepath.Join(t.TempDir(), "sing-box")
	if err := os.WriteFile(executable, []byte("#!/bin/sh\nexit 0\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	service, err := NewWorkspaceServiceWithPickers(context.Background(), &memoryStore{workspace: w}, nil, nil, func(core string) (string, error) {
		if core != "sing-box" {
			t.Fatalf("unexpected core picker: %s", core)
		}
		return executable, nil
	}, nil)
	if err != nil {
		t.Fatal(err)
	}
	selected, err := service.PickCoreExecutable("sing-box")
	if err != nil {
		t.Fatal(err)
	}
	if selected != executable {
		t.Fatalf("unexpected selected executable: %q", selected)
	}
	service.selectExecutable = func(string) (string, error) { return "", nil }
	cancelled, err := service.PickCoreExecutable("sing-box")
	if err != nil || cancelled != "" {
		t.Fatal("cancelling the picker returned a selected path")
	}
}

func TestUpdateChainRejectsBasePortCollisionWithoutChangingState(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "node", Name: "Node", Protocol: domain.ProtocolSOCKS5, Server: "localhost", Port: 1080}}
	w.Chains = []domain.Chain{{ID: "route", Name: "Route", HopNodeIDs: []string{"node"}}}
	w.PortBindings = []domain.PortBinding{{ID: "binding", ChainID: "route", ListenHost: "127.0.0.1", ListenPort: 20001}}
	store := &memoryStore{workspace: w}
	service, err := NewWorkspaceServiceWithStore(context.Background(), store)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.UpdateChain(UpdateChainInput{ID: "route", Name: "Route", HopNodeIDs: []string{"node"}, ListenPort: w.Settings.BaseListenPort}); err == nil {
		t.Fatal("expected Base port collision")
	}
	if service.GetWorkspace().PortBindings[0].ListenPort != 20001 {
		t.Fatal("failed update mutated the live workspace")
	}
}

func TestImportLegacyStateFilePersistsWithoutDeletingSource(t *testing.T) {
	legacyPath := filepath.Join(t.TempDir(), "state.json")
	data := []byte(`{"nodes":[{"node_id":"node","name":"Node","node_type":"socks5","server":"localhost","port":1080}],"active_base_node_id":"node"}`)
	if err := os.WriteFile(legacyPath, data, 0o600); err != nil {
		t.Fatal(err)
	}
	store := &memoryStore{workspace: domain.DefaultWorkspace()}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), store, nil, func() (string, error) { return legacyPath, nil }, nil)
	if err != nil {
		t.Fatal(err)
	}
	report, err := service.ImportLegacyStateFile()
	if err != nil {
		t.Fatal(err)
	}
	if report.Nodes != 1 || service.GetWorkspace().ActiveNodeID != "node" {
		t.Fatalf("legacy import was not applied: %+v", report)
	}
	if _, err := os.Stat(legacyPath); err != nil {
		t.Fatalf("source state.json was removed: %v", err)
	}
	if len(store.workspace.Nodes) != 1 {
		t.Fatal("imported workspace was not persisted")
	}
}

func TestImportLegacyStateFileDoesNotOverwriteNonEmptyWorkspace(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "existing", Name: "Existing", Protocol: domain.ProtocolSOCKS5, Server: "localhost", Port: 1080}}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), &memoryStore{workspace: w}, nil, func() (string, error) { t.Fatal("file picker must not be called"); return "", nil }, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.ImportLegacyStateFile(); err == nil {
		t.Fatal("expected non-empty workspace import to be rejected")
	}
}

func TestStartCoreValidatesConfigAndStreamsRedactedLogs(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell-script fake core is Unix-only")
	}
	dir := t.TempDir()
	fake := filepath.Join(dir, "fake-sing-box")
	script := "#!/bin/sh\nif [ \"$1\" = \"check\" ]; then exit 0; fi\necho fake-core-started\nsleep 10\n"
	if err := os.WriteFile(fake, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	w := domain.DefaultWorkspace()
	w.Settings.ConfigOutputDir = dir
	w.Settings.Core.Executable["sing-box"] = fake
	w.Nodes = []domain.Node{{ID: "base", Name: "Base", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080}}
	w.ActiveNodeID = "base"
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	if err := service.StartCore(); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for service.GetRuntimeStatus().Status != "running" && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if service.GetRuntimeStatus().Status != "running" {
		t.Fatalf("fake core did not start: %+v", service.GetRuntimeStatus())
	}
	deadline = time.Now().Add(2 * time.Second)
	for !strings.Contains(strings.Join(service.GetRuntimeLogs(), "\n"), "fake-core-started") && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if !strings.Contains(strings.Join(service.GetRuntimeLogs(), "\n"), "fake-core-started") {
		t.Fatal("core stdout was not captured")
	}
	if err := service.StopCore(); err != nil {
		t.Fatal(err)
	}
}

func TestDeleteNodeRejectsChainReferencesAndRemovesUnusedNode(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "entry", Name: "Entry", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080}, {ID: "unused", Name: "Unused", Protocol: domain.ProtocolHTTP, Server: "127.0.0.1", Port: 8080}}
	w.Chains = []domain.Chain{{ID: "route", Name: "Route", HopNodeIDs: []string{"entry"}}}
	w.PortBindings = []domain.PortBinding{{ID: "port", ChainID: "route", ListenHost: "127.0.0.1", ListenPort: 23001}}
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.DeleteNode("entry"); err == nil {
		t.Fatal("expected referenced Base Node deletion to fail")
	}
	updated, err := service.DeleteNode("unused")
	if err != nil {
		t.Fatal(err)
	}
	if len(updated.Nodes) != 1 || updated.Nodes[0].ID != "entry" {
		t.Fatalf("unused Base Node not deleted: %+v", updated.Nodes)
	}
}

func TestUpdateSettingsRegistersAndRemovesSystemStartup(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: domain.DefaultWorkspace()})
	if err != nil {
		t.Fatal(err)
	}
	settings := service.GetWorkspace().Settings
	settings.RunOnStartup = true
	if _, err := service.UpdateSettings(settings); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(home, ".config", "autostart", "chainport-gateway.desktop")
	if _, err := os.Stat(path); err != nil {
		t.Fatalf("startup entry was not created: %v", err)
	}
	settings.RunOnStartup = false
	if _, err := service.UpdateSettings(settings); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("startup entry was not removed")
	}
}

func TestCoreCommandProfiles(t *testing.T) {
	for _, test := range []struct {
		name         string
		check, start []string
	}{{"sing-box", []string{"sing-box", "check", "-c", "config"}, []string{"sing-box", "run", "-c", "config"}}, {"xray", []string{"xray", "run", "-test", "-c", "config"}, []string{"xray", "run", "-c", "config"}}, {"mihomo", []string{"mihomo", "-t", "-f", "config"}, []string{"mihomo", "-f", "config"}}} {
		check, start, err := coreCommands(test.name, test.name, "config")
		if err != nil {
			t.Fatal(err)
		}
		if strings.Join(check, " ") != strings.Join(test.check, " ") || strings.Join(start, " ") != strings.Join(test.start, " ") {
			t.Fatalf("wrong commands for %s: %v / %v", test.name, check, start)
		}
	}
}
