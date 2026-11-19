package migration

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
)

type testSecretStore struct {
	values    map[string]string
	available bool
}

func (s *testSecretStore) Available() bool { return s.available }
func (s *testSecretStore) Put(_ context.Context, reference, value string) error {
	s.values[reference] = value
	return nil
}
func (s *testSecretStore) Get(_ context.Context, reference string) (string, error) {
	return s.values[reference], nil
}
func (s *testSecretStore) Delete(_ context.Context, reference string) error {
	delete(s.values, reference)
	return nil
}

func TestImportLegacyStateMovesSecretsAndPreservesWholeChainTUN(t *testing.T) {
	data := []byte(`{
  "subscriptions":[{"sub_id":"sub-1","name":"Airport","url":"https://feed.example/sub?token=URL_SECRET","sub_type":"auto","enable_update":true,"update_interval":60,"http_headers":{"Authorization":"HEADER_SECRET"},"remarks_memo":"keep memo"}],
  "nodes":[{"node_id":"entry","name":"Entry","node_type":"vless","server":"entry.example","port":443,"uuid_str":"UUID_SECRET","password":"PASSWORD_SECRET","network":"tcp","extra":{"private":"EXTRA_SECRET"},"raw_dict":{"token":"RAW_SECRET"},"source_sub":"Airport"},{"node_id":"exit","name":"Exit","node_type":"socks5","server":"exit.example","port":1080}],
  "chains":[{"chain_id":"route","name":"Entry to Exit","hop_node_ids":["entry","exit"]}],
  "port_mappings":[{"mapping_id":"port-route","chain_id":"route","listen_host":"127.0.0.1","listen_port":23001,"remark":"preserve"}],
  "active_base_node_id":"entry","tun_chain_id":"route","enable_tun":true,"base_node_listen_port":10808,"core_type":"sing-box","enable_udp":true
}`)
	secrets := &testSecretStore{values: map[string]string{}, available: true}
	workspace, report, err := ImportLegacyState(context.Background(), data, secrets)
	if err != nil {
		t.Fatal(err)
	}
	if len(workspace.Nodes) != 2 || len(workspace.Chains) != 1 || workspace.TUN.Kind != "chain" || workspace.TUN.TargetID != "route" || !workspace.TUN.Enabled {
		t.Fatalf("legacy route/TUN was not preserved: %+v", workspace)
	}
	if workspace.Chains[0].HopNodeIDs[0] != "entry" || workspace.Chains[0].HopNodeIDs[1] != "exit" {
		t.Fatal("hop order changed during import")
	}
	if workspace.PortBindings[0].ListenPort != 23001 || workspace.PortBindings[0].Remark != "preserve" {
		t.Fatalf("port binding was not preserved: %+v", workspace.PortBindings[0])
	}
	if workspace.Nodes[0].SourceID != "sub-1" || workspace.Subscriptions[0].URLSecretRef == "" || workspace.Subscriptions[0].HeaderSecretRefs["Authorization"] == "" {
		t.Fatal("subscription secret references were not mapped")
	}
	metadataSecret, ok := secrets.values[workspace.Nodes[0].SourceMetadataRef]
	if !ok {
		t.Fatal("protocol-specific node metadata was not moved to the credential vault")
	}
	decodedMetadata, err := security.DecodeMetadataJSON(metadataSecret)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(decodedMetadata), "EXTRA_SECRET") {
		t.Fatal("runtime node.extra metadata was not preserved")
	}
	encoded, err := json.Marshal(workspace)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{"URL_SECRET", "HEADER_SECRET", "UUID_SECRET", "PASSWORD_SECRET", "EXTRA_SECRET", "RAW_SECRET"} {
		if strings.Contains(string(encoded), secret) {
			t.Fatalf("plaintext secret %q leaked into migrated workspace", secret)
		}
	}
	if workspace.Subscriptions[0].LegacyMetadataRef == "" || secrets.values[workspace.Subscriptions[0].LegacyMetadataRef] == "" {
		t.Fatal("legacy subscription metadata was not preserved in the OS vault")
	}
	if len(secrets.values) != 6 || report.SecretsMoved != 6 {
		t.Fatalf("expected 6 secrets in OS vault, got %d / %d", len(secrets.values), report.SecretsMoved)
	}
}

func TestImportLegacyStateRefusesPlaintextSecretFallback(t *testing.T) {
	data := []byte(`{"nodes":[{"node_id":"node","name":"Node","node_type":"socks5","server":"localhost","port":1080,"password":"must-not-be-plaintext"}]}`)
	if _, _, err := ImportLegacyState(context.Background(), data, nil); err == nil {
		t.Fatal("expected import to fail when the OS secret vault is unavailable")
	}
}

func TestImportLegacyStateAllocatesMissingChainPortWithoutCollidingWithBase(t *testing.T) {
	data := []byte(`{"nodes":[{"node_id":"n","name":"Node","node_type":"socks5","server":"localhost","port":1080}],"chains":[{"chain_id":"c","name":"Chain","hop_node_ids":["n"]}],"base_node_listen_port":20001}`)
	workspace, report, err := ImportLegacyState(context.Background(), data, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(workspace.PortBindings) != 1 || workspace.PortBindings[0].ListenPort != 20002 {
		t.Fatalf("missing Chain port was not allocated safely: %+v", workspace.PortBindings)
	}
	if len(report.Warnings) == 0 {
		t.Fatal("expected a migration warning for the allocated port")
	}
}

func TestImportLegacyStateRollsBackSecretsWhenValidationFails(t *testing.T) {
	data := []byte(`{"subscriptions":[{"sub_id":"sub","name":"Feed","url":"https://feed.example/?token=secret"}],"chains":[{"chain_id":"broken","name":"Broken","hop_node_ids":["missing"]}]}`)
	secrets := &testSecretStore{values: map[string]string{}, available: true}
	if _, _, err := ImportLegacyState(context.Background(), data, secrets); err == nil {
		t.Fatal("expected invalid Chain reference to fail import")
	}
	if len(secrets.values) != 0 {
		t.Fatalf("secret vault entries were not rolled back: %d", len(secrets.values))
	}
}

func TestImportLegacyStateRejectsUnrelatedJSON(t *testing.T) {
	if _, _, err := ImportLegacyState(context.Background(), []byte(`{"hello":"world"}`), nil); err == nil {
		t.Fatal("expected unrelated JSON to be rejected")
	}
}

func TestImportLegacyStateExpandsLegacyChainWrapperNodes(t *testing.T) {
	data := []byte(`{"nodes":[{"node_id":"a","name":"A","node_type":"socks5","server":"a.example","port":1080},{"node_id":"b","name":"B","node_type":"socks5","server":"b.example","port":1081},{"node_id":"wrapper","name":"Wrapped","node_type":"chain","server":"127.0.0.1","port":20001,"extra":{"source_chain_id":"inner-chain","chain_hop_node_ids":["a","b"]}}],"chains":[{"chain_id":"outer-chain","name":"Outer","hop_node_ids":["wrapper"]}]}`)
	workspace, report, err := ImportLegacyState(context.Background(), data, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(workspace.Nodes) != 2 || len(workspace.Chains) != 2 {
		t.Fatalf("legacy wrapper migration lost nodes/chains: %+v", workspace)
	}
	for _, chain := range workspace.Chains {
		if len(chain.HopNodeIDs) != 2 || chain.HopNodeIDs[0] != "a" || chain.HopNodeIDs[1] != "b" {
			t.Fatalf("legacy wrapper hops were not expanded in order: %+v", chain)
		}
	}
	if report.Chains != 2 {
		t.Fatalf("migration report chain count incorrect: %+v", report)
	}
}

func TestImportLegacyStateSupportsOlderAutoUpdateIntervalField(t *testing.T) {
	data := []byte(`{"subscriptions":[{"sub_id":"old-sub","name":"Old Feed","url":"https://feed.example/sub","auto_update_interval":45}],"nodes":[]}`)
	secrets := &testSecretStore{values: map[string]string{}, available: true}
	workspace, _, err := ImportLegacyState(context.Background(), data, secrets)
	if err != nil {
		t.Fatal(err)
	}
	if len(workspace.Subscriptions) != 1 || workspace.Subscriptions[0].UpdateMinutes != 45 {
		t.Fatalf("legacy auto_update_interval was not migrated: %+v", workspace.Subscriptions)
	}
}

func TestImportLegacyStatePreservesUsableCoreExecutablePaths(t *testing.T) {
	dir := t.TempDir()
	binary := filepath.Join(dir, "sing-box")
	if err := os.WriteFile(binary, []byte("test executable"), 0o700); err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(map[string]any{"core_type": "sing-box", "core_exe_paths": map[string]string{"sing-box": binary}})
	workspace, _, err := ImportLegacyState(context.Background(), encoded, nil)
	if err != nil {
		t.Fatal(err)
	}
	if workspace.Settings.Core.Executable["sing-box"] != binary {
		t.Fatalf("usable legacy core executable path was discarded: %+v", workspace.Settings.Core.Executable)
	}
}

func TestImportLegacyStateSupportsSingleLegacyCoreExecutablePath(t *testing.T) {
	dir := t.TempDir()
	binary := filepath.Join(dir, "xray")
	if err := os.WriteFile(binary, []byte("test executable"), 0o700); err != nil {
		t.Fatal(err)
	}
	encoded, _ := json.Marshal(map[string]any{"core_type": "xray", "core_exe_path": binary})
	workspace, _, err := ImportLegacyState(context.Background(), encoded, nil)
	if err != nil {
		t.Fatal(err)
	}
	if workspace.Settings.Core.Executable["xray"] != binary {
		t.Fatalf("single legacy core executable path was not migrated: %+v", workspace.Settings.Core.Executable)
	}
}
