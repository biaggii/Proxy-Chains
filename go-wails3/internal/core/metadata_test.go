package core

import (
	"context"
	"testing"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
)

type secretMap map[string]string

func (s secretMap) Available() bool                                   { return true }
func (s secretMap) Put(_ context.Context, key, value string) error    { s[key] = value; return nil }
func (s secretMap) Get(_ context.Context, key string) (string, error) { return s[key], nil }
func (s secretMap) Delete(_ context.Context, key string) error        { delete(s, key); return nil }

func TestResolveNodeExtraFromCredentialVault(t *testing.T) {
	secrets := secretMap{}
	encoded, err := security.EncodeMetadataJSON([]byte(`{"extra":{"plugin":"obfs-local","security":"tls"}}`))
	if err != nil {
		t.Fatal(err)
	}
	if err := secrets.Put(context.Background(), "node-meta", encoded); err != nil {
		t.Fatal(err)
	}
	extra, err := ResolveNodeExtra(context.Background(), domain.Node{SourceMetadataRef: "node-meta"}, secrets)
	if err != nil {
		t.Fatal(err)
	}
	if extra["plugin"] != "obfs-local" || extra["security"] != "tls" {
		t.Fatalf("unexpected node extra: %#v", extra)
	}
}
