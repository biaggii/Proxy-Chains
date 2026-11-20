package service

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
)

func TestEncryptedProfileBackupRoundTripAndRejectsWrongPassword(t *testing.T) {
	payload := []byte(`{"workspace":{"nodes":[]},"secrets":{"password":"secret-value"}}`)
	encrypted, err := encryptProfileBackup(payload, "correct horse battery staple")
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encrypted), "secret-value") {
		t.Fatal("backup leaked plaintext credential")
	}
	plain, err := decryptProfileBackup(encrypted, "correct horse battery staple")
	if err != nil {
		t.Fatal(err)
	}
	if string(plain) != string(payload) {
		t.Fatalf("backup payload changed: %s", plain)
	}
	if _, err := decryptProfileBackup(encrypted, "incorrect password"); err == nil {
		t.Fatal("wrong password should fail")
	}
	var envelope encryptedProfileBackup
	if err := json.Unmarshal(encrypted, &envelope); err != nil {
		t.Fatal(err)
	}
	envelope.Ciphertext = envelope.Ciphertext[:len(envelope.Ciphertext)-4] + "AAAA"
	tampered, _ := json.Marshal(envelope)
	if _, err := decryptProfileBackup(tampered, "correct horse battery staple"); err == nil {
		t.Fatal("tampered backup should fail authentication")
	}
}

func TestWorkspaceSecretReferencesAndRemapping(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "n", Name: "Node", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080, Credentials: domain.Credentials{UsernameRef: "user", PasswordRef: "pass"}, SourceMetadataRef: "metadata"}}
	w.Subscriptions = []domain.Subscription{{ID: "sub", Name: "Feed", URLSecretRef: "url", HeaderSecretRefs: map[string]string{"Authorization": "header"}, LegacyMetadataRef: "legacy"}}
	refs := workspaceSecretReferences(w)
	if len(refs) != 6 {
		t.Fatalf("expected six unique secret references, got %v", refs)
	}
	rewriteWorkspaceSecretReferences(&w, map[string]string{"user": "new-user", "pass": "new-pass", "metadata": "new-metadata", "url": "new-url", "header": "new-header", "legacy": "new-legacy"})
	if w.Nodes[0].Credentials.UsernameRef != "new-user" || w.Nodes[0].Credentials.PasswordRef != "new-pass" || w.Nodes[0].SourceMetadataRef != "new-metadata" {
		t.Fatalf("node refs were not remapped: %+v", w.Nodes[0])
	}
	if w.Subscriptions[0].URLSecretRef != "new-url" || w.Subscriptions[0].HeaderSecretRefs["Authorization"] != "new-header" || w.Subscriptions[0].LegacyMetadataRef != "new-legacy" {
		t.Fatalf("subscription refs were not remapped: %+v", w.Subscriptions[0])
	}
}

func TestPBKDF2SHA256KnownVector(t *testing.T) {
	got := pbkdf2SHA256([]byte("password"), []byte("salt"), 1, 32)
	const expected = "120fb6cffcf8b32c43e7225256c4f837a86548c92ccc35480805987cb70be17b"
	if fmt.Sprintf("%x", got) != expected {
		t.Fatalf("PBKDF2 mismatch: %x", got)
	}
}
