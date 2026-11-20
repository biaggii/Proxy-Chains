package service

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/profiles"
)

func TestWorkspaceServiceProfileLifecycleAndDataMove(t *testing.T) {
	base := t.TempDir()
	startupHome := filepath.Join(base, "home")
	if err := os.MkdirAll(startupHome, 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("HOME", startupHome)
	manager, err := profiles.Open(filepath.Join(base, "data"), filepath.Join(base, "location.json"))
	if err != nil {
		t.Fatal(err)
	}
	defer manager.Close()
	secrets := subscriptionSecrets{}
	service, err := NewWorkspaceServiceWithDependencies(context.Background(), manager, secrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	defaultWorkspace := service.GetWorkspace()
	defaultWorkspace.Nodes = []domain.Node{{ID: "default-node", Name: "Default", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080}}
	if _, err := service.commit(defaultWorkspace); err != nil {
		t.Fatal(err)
	}
	state, err := service.CreateProfile("Work")
	if err != nil {
		t.Fatal(err)
	}
	var workID string
	for _, p := range state.Profiles {
		if p.Name == "Work" {
			workID = p.ID
		}
	}
	workspace, state, err := service.SwitchProfile(workID)
	if err != nil {
		t.Fatal(err)
	}
	if len(workspace.Nodes) != 0 || state.ActiveProfileID != workID {
		t.Fatal("new profile did not open as an independent workspace")
	}
	secrets["work-secret"] = "profile-credential"
	workspace.Nodes = []domain.Node{{ID: "work-node", Name: "Work", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1081, Credentials: domain.Credentials{PasswordRef: "work-secret"}}}
	workspace.Settings.RunOnStartup = true
	if _, err := service.commit(workspace); err != nil {
		t.Fatal(err)
	}
	state, err = service.MoveDataLocation(filepath.Join(base, "moved"))
	if err != nil {
		t.Fatal(err)
	}
	if state.DataLocation != filepath.Join(base, "moved") {
		t.Fatalf("data location did not change: %+v", state)
	}
	workspace, state, err = service.SwitchProfile("default")
	if err != nil {
		t.Fatal(err)
	}
	if len(workspace.Nodes) != 1 || workspace.Nodes[0].ID != "default-node" {
		t.Fatalf("default workspace was not preserved: %+v", workspace.Nodes)
	}
	startupPath := filepath.Join(startupHome, ".config", "autostart", "chainport-gateway.desktop")
	if _, err := os.Stat(startupPath); !os.IsNotExist(err) {
		t.Fatal("switching to a profile with startup disabled should remove the OS startup entry")
	}
	if _, err := service.DeleteProfile("default"); err == nil {
		t.Fatal("default profile must not be deletable")
	}
	if _, err := service.DeleteProfile(workID); err != nil {
		t.Fatal(err)
	}
	if _, ok := secrets["work-secret"]; ok {
		t.Fatal("deleting a profile should remove its OS-vault credentials")
	}
}

func TestSettingsExportAndImport(t *testing.T) {
	initial := domain.DefaultWorkspace()
	initial.Settings.Core.Executable["sing-box"] = "/usr/bin/sing-box"
	initial.Settings.ConfigOutputDir = "/tmp/chainport-runtime"
	store := &memoryStore{workspace: initial}
	service, err := NewWorkspaceServiceWithStore(context.Background(), store)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "settings.json")
	ConfigureFileDialogs(service, nil, func(string) (string, error) { return path, nil }, func(string) (string, error) { return path, nil })
	if err := service.ExportSettings(); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var file settingsFile
	if err := json.Unmarshal(data, &file); err != nil {
		t.Fatal(err)
	}
	if len(file.Settings.Core.Executable) != 0 || file.Settings.ConfigOutputDir != "" {
		t.Fatal("portable settings export should omit machine-local paths")
	}
	file.Settings.BaseListenPort = 12080
	file.Settings.Network.BootstrapDNS = "8.8.8.8"
	data, err = json.Marshal(file)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	updated, err := service.ImportSettings()
	if err != nil {
		t.Fatal(err)
	}
	if updated.Settings.BaseListenPort != 12080 || updated.Settings.Network.BootstrapDNS != "8.8.8.8" || updated.Settings.Core.Executable["sing-box"] != "/usr/bin/sing-box" || updated.Settings.ConfigOutputDir != "/tmp/chainport-runtime" {
		t.Fatalf("settings import did not apply: %+v", updated.Settings)
	}
}

func TestEncryptedProfileBackupRestoresWorkspaceAndSecrets(t *testing.T) {
	sourceSecrets := subscriptionSecrets{"node-user": "alice", "node-password": "correct-secret"}
	sourceWorkspace := domain.DefaultWorkspace()
	sourceWorkspace.Nodes = []domain.Node{{ID: "node", Name: "Imported", Protocol: domain.ProtocolSOCKS5, Server: "proxy.example", Port: 1080, Credentials: domain.Credentials{UsernameRef: "node-user", PasswordRef: "node-password"}}}
	sourceStore := &memoryStore{workspace: sourceWorkspace}
	source, err := NewWorkspaceServiceWithDependencies(context.Background(), sourceStore, sourceSecrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "profile.cpbackup")
	ConfigureFileDialogs(source, nil, nil, func(string) (string, error) { return path, nil })
	if exported, err := source.ExportProfileBackup("a long test password 123"); err != nil || !exported {
		t.Fatalf("profile backup export failed: exported=%v err=%v", exported, err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) == "" || containsBytes(raw, []byte("correct-secret")) {
		t.Fatal("encrypted profile backup leaked credentials")
	}
	targetSecrets := subscriptionSecrets{}
	targetStore := &memoryStore{workspace: domain.DefaultWorkspace()}
	target, err := NewWorkspaceServiceWithDependencies(context.Background(), targetStore, targetSecrets, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	ConfigureFileDialogs(target, nil, func(string) (string, error) { return path, nil }, nil)
	if _, err := target.ImportProfileBackup("wrong password 123"); err == nil {
		t.Fatal("incorrect backup password should fail")
	}
	restored, err := target.ImportProfileBackup("a long test password 123")
	if err != nil {
		t.Fatal(err)
	}
	if len(restored.Nodes) != 1 {
		t.Fatalf("restored profile lost nodes: %+v", restored.Nodes)
	}
	if targetSecrets[restored.Nodes[0].Credentials.UsernameRef] != "alice" || targetSecrets[restored.Nodes[0].Credentials.PasswordRef] != "correct-secret" {
		t.Fatal("restored credentials were not remapped into the destination OS vault")
	}
}

func containsBytes(haystack, needle []byte) bool { return bytes.Contains(haystack, needle) }
