package parser

import (
	"context"
	"testing"
)

func TestParseClashYAMLAndPreserveProtocolMetadata(t *testing.T) {
	input := `proxies:
  - name: VMess WS
    type: vmess
    server: vmess.example
    port: 443
    uuid: vmess-id
    alterId: 0
    cipher: auto
    tls: true
    servername: cdn.example
    network: ws
    ws-opts:
      path: /edge
      headers:
        Host: cdn.example
  - name: Trojan
    type: trojan
    server: trojan.example
    port: 443
    password: trojan-password
    sni: trojan.example
  - name: Shadowsocks plugin
    type: ss
    server: ss.example
    port: 8388
    cipher: chacha20-ietf-poly1305
    password: ss-password
    plugin: obfs
    plugin-opts:
      mode: tls
      host: cdn.example
  - name: VLESS XHTTP
    type: vless
    server: xhttp.example
    port: 443
    uuid: xhttp-uuid
    tls: true
    network: xhttp
    xhttp-opts:
      path: /api
      host: cdn.example
      mode: stream-up
      x-padding-bytes: 100-1000
`
	secrets := memorySecrets{}
	nodes, errs := ParseClashYAML(context.Background(), input, "sub-clash", secrets)
	if len(errs) != 0 {
		t.Fatalf("unexpected Clash errors: %v", errs)
	}
	if len(nodes) != 4 {
		t.Fatalf("expected 4 Clash nodes, got %d", len(nodes))
	}
	if nodes[0].Transport.Network != "ws" || nodes[0].Transport.Path != "/edge" || nodes[0].Transport.Host != "cdn.example" {
		t.Fatalf("VMess WS metadata lost: %+v", nodes[0])
	}
	if nodes[1].Credentials.PasswordRef == "" || !nodes[1].TLS.Enabled {
		t.Fatalf("Trojan fields lost: %+v", nodes[1])
	}
	if nodes[2].Cipher != "chacha20-ietf-poly1305" || nodes[2].SourceMetadataRef == "" {
		t.Fatalf("SS plugin metadata lost: %+v", nodes[2])
	}
	if nodes[3].Transport.Network != "xhttp" || nodes[3].Transport.Path != "/api" || nodes[3].Transport.Host != "cdn.example" || nodes[3].SourceMetadataRef == "" {
		t.Fatalf("XHTTP options lost: %+v", nodes[3])
	}
}

func TestParseClashYAMLReturnsPerProxyErrors(t *testing.T) {
	nodes, errs := ParseClashYAML(context.Background(), "proxies:\n  - name: bad\n    type: hysteria2\n    server: example.com\n    port: 443\n", "", memorySecrets{})
	if len(nodes) != 0 || len(errs) != 1 {
		t.Fatalf("expected one unsupported-protocol error: %v", errs)
	}
}

func TestParseClashWireGuardPreservesSensitiveAndPeerMetadata(t *testing.T) {
	input := `proxies:
  - name: WireGuard
    type: wireguard
    server: wg.example
    port: 51820
    ip: 10.0.0.2
    ipv6: fd00::2
    private-key: private-key
    public-key: public-key
    preshared-key: preshared-key
    allowed-ips:
      - 0.0.0.0/0
      - ::/0
    reserved: [1, 2, 3]
    mtu: 1380
`
	secrets := memorySecrets{}
	nodes, errs := ParseClashYAML(context.Background(), input, "wg-feed", secrets)
	if len(errs) != 0 || len(nodes) != 1 {
		t.Fatalf("parse errors: %v", errs)
	}
	if nodes[0].Credentials.PrivateKeyRef == "" || secrets[nodes[0].Credentials.PrivateKeyRef] != "private-key" || nodes[0].WGPublicKey != "public-key" || nodes[0].WGLocalAddress != "10.0.0.2" {
		t.Fatalf("WireGuard fields missing: %+v", nodes[0])
	}
	if nodes[0].SourceMetadataRef == "" {
		t.Fatal("WireGuard peer metadata was not preserved in the vault")
	}
}
