package parser

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
	"strings"
	"testing"
)

type memorySecrets map[string]string

func (m memorySecrets) Available() bool                                { return true }
func (m memorySecrets) Put(_ context.Context, key, value string) error { m[key] = value; return nil }
func (m memorySecrets) Delete(_ context.Context, key string) error     { delete(m, key); return nil }

func TestParseShareLinksProtocolsAndCredentialReferences(t *testing.T) {
	vmessJSON := `{"ps":"VMess Edge","add":"vmess.example","port":443,"id":"vmess-uuid","aid":0,"net":"ws","host":"cdn.example","path":"/edge","tls":"tls","sni":"cdn.example","alpn":["h2","http/1.1"]}`
	vmess := "vmess://" + base64.RawStdEncoding.EncodeToString([]byte(vmessJSON))
	links := strings.Join([]string{
		vmess,
		"vless://vless-uuid@vless.example:443?type=ws&security=tls&sni=cdn.example&host=cdn.example&path=%2Fvless&flow=xtls-rprx-vision#VLESS",
		"trojan://trojan-password@trojan.example:443?sni=trojan.example#Trojan",
		"ss://" + base64.RawStdEncoding.EncodeToString([]byte("chacha20-ietf-poly1305:ss-password")) + "@ss.example:8388#Shadowsocks",
		"socks5://user:pass@socks.example:1080#SOCKS",
		"https://user:pass@http.example:443#HTTPS",
	}, "\n")
	secrets := memorySecrets{}
	nodes, errs := ParseShareLinks(context.Background(), links, "sub-1", secrets)
	if len(errs) != 0 {
		t.Fatalf("unexpected parse errors: %v", errs)
	}
	if len(nodes) != 6 {
		t.Fatalf("expected 6 nodes, got %d", len(nodes))
	}
	if nodes[0].Protocol != "vmess" || nodes[0].Transport.Network != "ws" || nodes[0].TLS.SNI != "cdn.example" {
		t.Fatalf("VMess fields lost: %+v", nodes[0])
	}
	if nodes[0].Security != "auto" {
		t.Fatalf("VMess cipher/security field lost: %+v", nodes[0])
	}
	if nodes[1].Protocol != "vless" || nodes[1].Flow != "xtls-rprx-vision" || nodes[1].Transport.Path != "/vless" {
		t.Fatalf("VLESS fields lost: %+v", nodes[1])
	}
	if nodes[2].Credentials.PasswordRef == "" || nodes[3].Cipher != "chacha20-ietf-poly1305" || nodes[4].Credentials.UsernameRef == "" || !nodes[5].TLS.Enabled {
		t.Fatal("credentials or protocol fields were not stored correctly")
	}
	for _, node := range nodes {
		if node.SourceID != "sub-1" {
			t.Fatalf("source ID not preserved: %+v", node)
		}
	}
	for _, secret := range []string{"vmess-uuid", "vless-uuid", "trojan-password", "ss-password", "user", "pass"} {
		found := false
		for _, value := range secrets {
			if value == secret {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("credential %q missing from secret store", secret)
		}
	}
}

func TestParseShareLinksPreservesRealityAndShadowsocksPluginOptions(t *testing.T) {
	links := "vless://reality-uuid@reality.example:443?type=grpc&security=reality&sni=www.example&flow=xtls-rprx-vision&pbk=public-key&sid=abcd&fp=chrome#Reality\n" + "ss://" + base64.RawStdEncoding.EncodeToString([]byte("aes-128-gcm:secret")) + "@ss.example:8388/?plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dcdn.example#SS"
	secrets := memorySecrets{}
	nodes, errs := ParseShareLinks(context.Background(), links, "feed", secrets)
	if len(errs) != 0 || len(nodes) != 2 {
		t.Fatalf("parse errors: %v", errs)
	}
	if nodes[0].SourceMetadataRef == "" || nodes[0].TLS.SNI != "www.example" {
		t.Fatalf("REALITY metadata not preserved: %+v", nodes[0])
	}
	metadataRef := nodes[1].SourceMetadataRef
	if metadataRef == "" {
		t.Fatal("Shadowsocks plugin metadata not preserved")
	}
	encoded := secrets[metadataRef]
	decoded, err := security.DecodeMetadataJSON(encoded)
	if err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(decoded, &payload); err != nil {
		t.Fatal(err)
	}
	extra := payload["extra"].(map[string]any)
	if extra["plugin"] != "obfs" || extra["plugin_opts"].(map[string]any)["host"] != "cdn.example" {
		t.Fatalf("plugin settings lost: %+v", extra)
	}
}

func TestParseShareLinksPreservesXHTTPTransportOptions(t *testing.T) {
	link := "vless://xhttp-uuid@xhttp.example:443?type=xhttp&security=tls&sni=cdn.example&host=cdn.example&path=%2Fapi&mode=stream-up&extra=%7B%22xPaddingBytes%22%3A%22100-1000%22%7D#XHTTP"
	nodes, errs := ParseShareLinks(context.Background(), link, "feed", memorySecrets{})
	if len(errs) != 0 || len(nodes) != 1 {
		t.Fatalf("parse errors: %v", errs)
	}
	if nodes[0].Transport.Network != "xhttp" || nodes[0].Transport.Host != "cdn.example" || nodes[0].Transport.Path != "/api" || nodes[0].SourceMetadataRef == "" {
		t.Fatalf("XHTTP metadata lost: %+v", nodes[0])
	}
}

func TestParseShareLinksReportsInvalidLines(t *testing.T) {
	nodes, errs := ParseShareLinks(context.Background(), "vless://missing-host\nnot-a-link", "", memorySecrets{})
	if len(nodes) != 0 || len(errs) != 2 {
		t.Fatalf("expected two per-line errors, got nodes=%d errors=%v", len(nodes), errs)
	}
}

func TestParseShareLinksRequiresSecretStoreForCredentials(t *testing.T) {
	_, errs := ParseShareLinks(context.Background(), "socks5://user:password@example.com:1080", "", nil)
	if len(errs) != 1 {
		t.Fatal("expected secret store requirement")
	}
}
