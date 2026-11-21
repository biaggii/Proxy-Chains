package core

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
	"gopkg.in/yaml.v3"
)

type adapterSecrets map[string]string

func (s adapterSecrets) Available() bool                                 { return true }
func (s adapterSecrets) Put(_ context.Context, k, v string) error        { s[k] = v; return nil }
func (s adapterSecrets) Get(_ context.Context, k string) (string, error) { return s[k], nil }
func (s adapterSecrets) Delete(_ context.Context, k string) error        { delete(s, k); return nil }

func adapterWorkspace() (domain.Workspace, adapterSecrets) {
	s := adapterSecrets{"entry-uuid": "entry-secret-uuid", "exit-password": "exit-secret-password"}
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{
		{ID: "entry", Name: "Entry", Protocol: domain.ProtocolVLESS, Server: "entry.example", Port: 443, Credentials: domain.Credentials{UUIDRef: "entry-uuid"}, Transport: domain.Transport{Network: "ws", Path: "/edge", Host: "cdn.example"}, TLS: domain.TLSOptions{Enabled: true, SNI: "cdn.example"}},
		{ID: "exit", Name: "Exit", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080, Credentials: domain.Credentials{PasswordRef: "exit-password"}, Transport: domain.Transport{Network: "tcp"}},
	}
	w.Chains = []domain.Chain{{ID: "route", Name: "Entry to Exit", HopNodeIDs: []string{"entry", "exit"}}}
	w.PortBindings = []domain.PortBinding{{ID: "route-port", ChainID: "route", ListenHost: "127.0.0.1", ListenPort: 23001}}
	return w, s
}

func TestGenerateAllCoreAdaptersWithOrderedChain(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.Settings.Network.EnableMux = true
	w.Settings.Network.EnableFragment = true
	w.Settings.Network.BlockQUIC = true
	w.Settings.Core.LogLevel = "trace"
	for _, coreName := range []string{"sing-box", "xray", "mihomo"} {
		t.Run(coreName, func(t *testing.T) {
			generated, err := GenerateConfig(context.Background(), w, coreName, secrets)
			if err != nil {
				t.Fatal(err)
			}
			if len(generated.Data) == 0 {
				t.Fatal("empty generated config")
			}
			switch coreName {
			case "sing-box":
				var config map[string]any
				if err := json.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				outbounds := config["outbounds"].([]any)
				first := findMap(outbounds, "CHAIN_route_H1")
				second := findMap(outbounds, "CHAIN_route_H2")
				if first == nil || second == nil || second["detour"] != "CHAIN_route_H1" {
					t.Fatalf("sing-box detour order incorrect: %s", generated.Data)
				}
				if first["uuid"] != "entry-secret-uuid" {
					t.Fatal("sing-box UUID secret was not resolved")
				}
				if first["multiplex"] != nil || first["tls"].(map[string]any)["fragment"] != true {
					t.Fatal("sing-box chained mux should be disabled while TLS fragment remains enabled")
				}
				if len(config["route"].(map[string]any)["rules"].([]any)) == 0 {
					t.Fatal("sing-box routing rules missing")
				}
				if config["log"].(map[string]any)["level"] != "trace" {
					t.Fatalf("sing-box log level was not normalized: %+v", config["log"])
				}
				dns := config["dns"].(map[string]any)
				if dns["final"] != "remote_dns_route" {
					t.Fatalf("sing-box DNS is not routed through the selected chain: %+v", dns)
				}
				servers := dns["servers"].([]any)
				hosts := findMap(servers, "hosts_dns")
				if hosts == nil || hosts["type"] != "hosts" {
					t.Fatalf("hosts DNS server tag does not match sing-box preferred_by rule: %+v", servers)
				}
				dnsRule := dns["rules"].([]any)[0].(map[string]any)
				if dnsRule["server"] != "hosts_dns" || dnsRule["preferred_by"] != "hosts_dns" {
					t.Fatalf("hosts DNS rule does not route to the tagged hosts server: %+v", dnsRule)
				}
				remoteDNS := findMap(servers, "remote_dns_route")
				if remoteDNS == nil || remoteDNS["domain_resolver"] != "hosts_dns" {
					t.Fatalf("DoH hostname is not resolved from the static hosts map: %+v", remoteDNS)
				}
				directDNS := findMap(servers, "direct_dns")
				if directDNS == nil || directDNS["domain_resolver"] != "local_dns" {
					t.Fatalf("direct bootstrap DNS resolver chain is missing: %+v", directDNS)
				}
			case "xray":
				var config map[string]any
				if err := json.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				outbounds := config["outbounds"].([]any)
				second := findMap(outbounds, "CHAIN_route_H2")
				if second == nil {
					t.Fatal("Xray second hop missing")
				}
				stream := second["streamSettings"].(map[string]any)
				sock := stream["sockopt"].(map[string]any)
				if sock["dialerProxy"] != "CHAIN_route_H1" {
					t.Fatalf("Xray dialer chain wrong: %+v", sock)
				}
				first := findMap(outbounds, "CHAIN_route_H1")
				if first["mux"] != nil || config["dns"] == nil {
					t.Fatal("Xray chained mux should be disabled while DNS configuration remains enabled")
				}
				if first["streamSettings"].(map[string]any)["finalmask"] == nil {
					t.Fatal("Xray TLS fragment mask missing")
				}
				if config["log"].(map[string]any)["loglevel"] != "debug" {
					t.Fatalf("Xray log level was not normalized: %+v", config["log"])
				}
				rules := config["routing"].(map[string]any)["rules"].([]any)
				found := false
				for _, item := range rules {
					if rule, ok := item.(map[string]any); ok && rule["inboundTag"] != nil && rule["outboundTag"] == "CHAIN_route_H2" {
						found = true
					}
				}
				if !found {
					t.Fatal("Xray DNS module is not routed through the selected chain")
				}
			case "mihomo":
				var config map[string]any
				if err := yaml.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				proxies := config["proxies"].([]any)
				second := findMap(proxies, "CHAIN_route_H2")
				if second == nil || second["dialer-proxy"] != "CHAIN_route_H1" {
					t.Fatalf("Mihomo dialer chain wrong: %s", generated.Data)
				}
				first := findMap(proxies, "CHAIN_route_H1")
				if config["dns"] == nil || first["smux"] != nil {
					t.Fatal("Mihomo chained smux should be disabled while DNS configuration remains enabled")
				}
				dns := config["dns"].(map[string]any)
				if !strings.Contains(dns["nameserver"].([]any)[0].(string), "#CHAIN_route_H2") {
					t.Fatalf("Mihomo DNS is not routed through selected chain: %+v", dns)
				}
			}
			if strings.Contains(string(generated.Data), "entry-uuid") || strings.Contains(string(generated.Data), "exit-password") {
				t.Fatal("credential reference leaked into core config")
			}
		})
	}
}

func TestGenerateAdaptersDisableMultiplexForEveryHopInMultiHopChains(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.Settings.Network.EnableMux = true
	w.Nodes[1].Protocol = domain.ProtocolShadowsocks
	w.Nodes[1].Cipher = "aes-256-gcm"
	for _, coreName := range []string{"sing-box", "xray", "mihomo"} {
		t.Run(coreName, func(t *testing.T) {
			generated, err := GenerateConfig(context.Background(), w, coreName, secrets)
			if err != nil {
				t.Fatal(err)
			}
			var first, second map[string]any
			switch coreName {
			case "sing-box":
				var config map[string]any
				if err := json.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				outbounds := config["outbounds"].([]any)
				first, second = findMap(outbounds, "CHAIN_route_H1"), findMap(outbounds, "CHAIN_route_H2")
				if first["multiplex"] != nil || second["multiplex"] != nil {
					t.Fatalf("sing-box multiplex must be disabled on every chained hop: first=%+v second=%+v", first, second)
				}
			case "xray":
				var config map[string]any
				if err := json.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				outbounds := config["outbounds"].([]any)
				first, second = findMap(outbounds, "CHAIN_route_H1"), findMap(outbounds, "CHAIN_route_H2")
				if first["mux"] != nil || second["mux"] != nil {
					t.Fatalf("Xray mux must be disabled on every chained hop: first=%+v second=%+v", first, second)
				}
			case "mihomo":
				var config map[string]any
				if err := yaml.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				proxies := config["proxies"].([]any)
				first, second = findMap(proxies, "CHAIN_route_H1"), findMap(proxies, "CHAIN_route_H2")
				if first["smux"] != nil || second["smux"] != nil {
					t.Fatalf("Mihomo smux must be disabled on every chained hop: first=%+v second=%+v", first, second)
				}
			}
		})
	}
}

func TestGenerateAdaptersKeepMultiplexForSingleNodeBaseRoute(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.Chains = nil
	w.PortBindings = nil
	w.ActiveNodeID = "entry"
	w.Settings.Network.EnableMux = true
	for _, coreName := range []string{"sing-box", "xray", "mihomo"} {
		generated, err := GenerateConfig(context.Background(), w, coreName, secrets)
		if err != nil {
			t.Fatal(err)
		}
		var outbound map[string]any
		switch coreName {
		case "sing-box":
			var config map[string]any
			if err := json.Unmarshal(generated.Data, &config); err != nil {
				t.Fatal(err)
			}
			outbound = findMap(config["outbounds"].([]any), "CHAIN___base___H1")
			if outbound["multiplex"] == nil {
				t.Fatalf("sing-box base node should retain mux: %+v", outbound)
			}
		case "xray":
			var config map[string]any
			if err := json.Unmarshal(generated.Data, &config); err != nil {
				t.Fatal(err)
			}
			outbound = findMap(config["outbounds"].([]any), "CHAIN___base___H1")
			if outbound["mux"] == nil {
				t.Fatalf("Xray base node should retain mux: %+v", outbound)
			}
		case "mihomo":
			var config map[string]any
			if err := yaml.Unmarshal(generated.Data, &config); err != nil {
				t.Fatal(err)
			}
			outbound = findMap(config["proxies"].([]any), "CHAIN___base___H1")
			if outbound["smux"] == nil {
				t.Fatalf("Mihomo base node should retain smux: %+v", outbound)
			}
		}
	}
}

func TestXrayBaseAndChainListenersUseMixedProtocol(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.ActiveNodeID = "entry"
	generated, err := GenerateConfig(context.Background(), w, "xray", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	inbounds := config["inbounds"].([]any)
	for _, expected := range []struct {
		tag  string
		port float64
	}{{"IN_BASE", float64(w.Settings.BaseListenPort)}, {"IN_23001", 23001}} {
		var found map[string]any
		for _, raw := range inbounds {
			inbound := raw.(map[string]any)
			if inbound["tag"] == expected.tag {
				found = inbound
				break
			}
		}
		if found == nil {
			t.Fatalf("missing Xray inbound %s: %+v", expected.tag, inbounds)
		}
		if found["protocol"] != "mixed" {
			t.Fatalf("Xray inbound %s should accept SOCKS and HTTP on one port: %+v", expected.tag, found)
		}
		if found["port"] != expected.port {
			t.Fatalf("Xray inbound %s port mismatch: %+v", expected.tag, found)
		}
	}
}

func TestGenerateAdaptersRejectUnsupportedXrayH2Transport(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.Nodes[0].Transport.Network = "h2"
	w.Chains[0].HopNodeIDs = []string{"entry"}
	if _, err := GenerateConfig(context.Background(), w, "xray", secrets); err == nil || !strings.Contains(err.Error(), "legacy") {
		t.Fatalf("expected explicit unsupported Xray H2 transport error, got %v", err)
	}
}

func TestAdaptersDoNotEmitNilShadowsocksPluginForOrdinaryNodes(t *testing.T) {
	for _, protocol := range []domain.Protocol{domain.ProtocolVMess, domain.ProtocolVLESS, domain.ProtocolTrojan, domain.ProtocolShadowsocks, domain.ProtocolSOCKS5, domain.ProtocolHTTP} {
		node := ResolvedNode{Domain: domain.Node{Protocol: protocol, Server: "proxy.example", Port: 443, Transport: domain.Transport{Network: "tcp"}}, UUID: "00000000-0000-0000-0000-000000000001", Password: "secret", Extra: map[string]any{}}
		sing, _, err := singBoxOutbound(node, "test", domain.DefaultWorkspace().Settings.Network)
		if err != nil {
			t.Fatalf("sing-box %s: %v", protocol, err)
		}
		if _, exists := sing["plugin"]; exists {
			t.Fatalf("sing-box %s unexpectedly emitted plugin: %#v", protocol, sing["plugin"])
		}
		mihomo, err := mihomoProxy(node, "test", domain.DefaultWorkspace().Settings.Network)
		if err != nil {
			t.Fatalf("Mihomo %s: %v", protocol, err)
		}
		if _, exists := mihomo["plugin"]; exists {
			t.Fatalf("Mihomo %s unexpectedly emitted plugin: %#v", protocol, mihomo["plugin"])
		}
	}
}

func TestHTTPSProxyEmitsTLSForAllCoreAdapters(t *testing.T) {
	node := ResolvedNode{Domain: domain.Node{Protocol: domain.ProtocolHTTP, Name: "HTTPS", Server: "proxy.example", Port: 8443, Transport: domain.Transport{Network: "tcp"}, TLS: domain.TLSOptions{Enabled: true, SNI: "proxy.example", ALPN: []string{"h2"}}}, Username: "user", Password: "password", Extra: map[string]any{}}
	network := domain.DefaultWorkspace().Settings.Network
	sing, _, err := singBoxOutbound(node, "https-test", network)
	if err != nil {
		t.Fatal(err)
	}
	if tls, ok := sing["tls"].(map[string]any); !ok || tls["enabled"] != true || tls["server_name"] != "proxy.example" {
		t.Fatalf("sing-box HTTPS proxy TLS missing: %+v", sing)
	}
	xray, err := xrayOutbound(node, "https-test", network)
	if err != nil {
		t.Fatal(err)
	}
	stream := xray["streamSettings"].(map[string]any)
	if stream["security"] != "tls" || stream["tlsSettings"].(map[string]any)["serverName"] != "proxy.example" {
		t.Fatalf("Xray HTTPS proxy TLS missing: %+v", xray)
	}
	mihomo, err := mihomoProxy(node, "https-test", network)
	if err != nil {
		t.Fatal(err)
	}
	if mihomo["tls"] != true || mihomo["servername"] != "proxy.example" {
		t.Fatalf("Mihomo HTTPS proxy TLS missing: %+v", mihomo)
	}
}

func TestSingBoxUsesDefaultDomainResolverForProxyServerHosts(t *testing.T) {
	w, secrets := adapterWorkspace()
	generated, err := GenerateConfig(context.Background(), w, "sing-box", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	route := config["route"].(map[string]any)
	resolver, ok := route["default_domain_resolver"].(map[string]any)
	if !ok || resolver["server"] != "direct_dns" || resolver["strategy"] != "ipv4_only" {
		t.Fatalf("sing-box route is missing a default domain resolver: %+v", route)
	}
}

func TestSingBoxRoutesLocalhostAndLoopbackDirectForEveryInbound(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.ActiveNodeID = "entry"
	generated, err := GenerateConfig(context.Background(), w, "sing-box", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	rules := config["route"].(map[string]any)["rules"].([]any)
	index := func(match func(map[string]any) bool) int {
		for i, item := range rules {
			if rule, ok := item.(map[string]any); ok && match(rule) {
				return i
			}
		}
		return -1
	}
	localhost := index(func(r map[string]any) bool {
		return r["outbound"] == "DIRECT" && strings.Contains(fmt.Sprint(r["domain_suffix"]), "localhost")
	})
	loopback := index(func(r map[string]any) bool {
		return r["outbound"] == "DIRECT" && strings.Contains(fmt.Sprint(r["ip_cidr"]), "127.0.0.0/8") && strings.Contains(fmt.Sprint(r["ip_cidr"]), "::1/128") && strings.Contains(fmt.Sprint(r["ip_cidr"]), "0.0.0.0/8")
	})
	private := index(func(r map[string]any) bool { return r["outbound"] == "DIRECT" && r["ip_is_private"] == true })
	baseRoute := index(func(r map[string]any) bool { return strings.Contains(fmt.Sprint(r["inbound"]), "IN_BASE") })
	chainRoute := index(func(r map[string]any) bool { return strings.Contains(fmt.Sprint(r["inbound"]), "IN_23001") })
	if localhost < 0 || loopback < 0 || private < 0 || baseRoute < 0 || chainRoute < 0 || !(localhost < baseRoute && loopback < baseRoute && private < baseRoute && localhost < chainRoute && loopback < chainRoute && private < chainRoute) {
		t.Fatalf("local destinations must route DIRECT before base and Chain listener routes: %+v", rules)
	}
}

func TestXrayRoutesLocalhostAndPrivateDestinationsDirectBeforeListeners(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.ActiveNodeID = "entry"
	w.Settings.Network.EnableIPv6 = false
	w.Settings.Network.BlockQUIC = true
	generated, err := GenerateConfig(context.Background(), w, "xray", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	rules := config["routing"].(map[string]any)["rules"].([]any)
	index := func(match func(map[string]any) bool) int {
		for i, item := range rules {
			if rule, ok := item.(map[string]any); ok && match(rule) {
				return i
			}
		}
		return -1
	}
	localhost := index(func(r map[string]any) bool {
		return r["outboundTag"] == "DIRECT" && strings.Contains(fmt.Sprint(r["domain"]), "full:localhost")
	})
	private := index(func(r map[string]any) bool {
		return r["outboundTag"] == "DIRECT" && strings.Contains(fmt.Sprint(r["ip"]), "10.0.0.0/8") && strings.Contains(fmt.Sprint(r["ip"]), "127.0.0.0/8") && strings.Contains(fmt.Sprint(r["ip"]), "fc00::/7")
	})
	base := index(func(r map[string]any) bool {
		return r["outboundTag"] == "CHAIN___base___H1" && strings.Contains(fmt.Sprint(r["inboundTag"]), "IN_BASE")
	})
	if localhost < 0 || private < 0 || base < 0 || localhost >= base || private >= base || rules[0].(map[string]any)["inboundTag"] == nil {
		t.Fatalf("Xray local direct rules missing or ordered after listener routes: %+v", rules)
	}
	if rules[1].(map[string]any)["outboundTag"] != "DIRECT" || rules[2].(map[string]any)["outboundTag"] != "DIRECT" {
		t.Fatalf("IPv6/QUIC block rules must follow local direct rules: %+v", rules[:3])
	}
}

func TestMihomoListenersUseLocalBypassSubRulesBeforeChainFallback(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.ActiveNodeID = "entry"
	w.Settings.Network.BlockQUIC = true
	generated, err := GenerateConfig(context.Background(), w, "mihomo", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := yaml.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	listeners := config["listeners"].([]any)
	subRules := config["sub-rules"].(map[string]any)
	for _, item := range listeners {
		listener := item.(map[string]any)
		ruleName := listener["rule"].(string)
		if _, hasFixedProxy := listener["proxy"]; hasFixedProxy {
			t.Fatalf("listener %s still forces a proxy and bypasses routing rules: %+v", listener["name"], listener)
		}
		rules := subRules[ruleName].([]any)
		joined := strings.Join(anyStrings(rules), "\n")
		expectedFinal := "MATCH,CHAIN_route_H2"
		if listener["name"] == "IN_BASE" {
			expectedFinal = "MATCH,CHAIN___base___H1"
		}
		for _, expected := range []string{"DOMAIN-SUFFIX,localhost,DIRECT", "IP-CIDR,127.0.0.0/8,DIRECT,no-resolve", "IP-CIDR6,::1/128,DIRECT,no-resolve", "IP-CIDR,0.0.0.0/8,DIRECT,no-resolve", "AND,((NETWORK,UDP),(DST-PORT,443)),REJECT", expectedFinal} {
			if !strings.Contains(joined, expected) {
				t.Fatalf("Mihomo listener %s rule %s missing %q: %v", listener["name"], ruleName, expected, rules)
			}
		}
	}
}

func anyStrings(values []any) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		result = append(result, fmt.Sprint(value))
	}
	return result
}

func TestSingBoxFinalTLSRecordFragmentMatchesPythonRouteOptions(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.Settings.Network.EnableSniffing = true
	w.Settings.Network.EnableFinalFragment = true
	w.Settings.Network.BlockQUIC = true
	generated, err := GenerateConfig(context.Background(), w, "sing-box", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	rules := config["route"].(map[string]any)["rules"].([]any)
	index := func(match func(map[string]any) bool) int {
		for i, item := range rules {
			if rule, ok := item.(map[string]any); ok && match(rule) {
				return i
			}
		}
		return -1
	}
	sniff := index(func(r map[string]any) bool { return r["action"] == "sniff" })
	dnsHijack := index(func(r map[string]any) bool { return r["action"] == "hijack-dns" && r["type"] == "logical" })
	fragment := index(func(r map[string]any) bool {
		return r["action"] == "route-options" && r["tls_record_fragment"] == true && strings.Contains(strings.TrimSpace(fmt.Sprint(r["protocol"])), "tls")
	})
	quic := index(func(r map[string]any) bool { return r["action"] == "reject" && r["network"] != nil && r["port"] != nil })
	if sniff < 0 || dnsHijack < 0 || fragment < 0 || quic < 0 || !(sniff < dnsHijack && dnsHijack < fragment && fragment < quic) {
		t.Fatalf("Python-compatible sniff/DNS/TLS-fragment/QUIC rule order is missing: %+v", rules)
	}
}

func TestSingBoxFinalFragmentWithoutSniffingAppliesToAllTLS(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.Settings.Network.EnableSniffing = false
	w.Settings.Network.EnableFinalFragment = true
	generated, err := GenerateConfig(context.Background(), w, "sing-box", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	rules := config["route"].(map[string]any)["rules"].([]any)
	found := false
	for _, item := range rules {
		if rule, ok := item.(map[string]any); ok && rule["action"] == "route-options" && rule["tls_record_fragment"] == true {
			found = true
			if _, hasProtocol := rule["protocol"]; hasProtocol {
				t.Fatalf("fragment rule should not be protocol-scoped when sniffing is disabled: %+v", rule)
			}
		}
	}
	if !found {
		t.Fatal("final TLS record fragmentation route option is missing")
	}
}

func TestXHTTPTransportIsExplicitAcrossCoreAdapters(t *testing.T) {
	w, secrets := adapterWorkspace()
	node := w.Nodes[0]
	node.Transport = domain.Transport{Network: "xhttp", Path: "/api", Host: "cdn.example"}
	node.SourceMetadataRef = "xhttp-meta"
	w.Nodes[0] = node
	encoded, err := security.EncodeMetadataJSON([]byte(`{"extra":{"query":{"mode":["stream-up"],"extra":["{\"xPaddingBytes\":\"100-1000\"}"]}}}`))
	if err != nil {
		t.Fatal(err)
	}
	secrets["xhttp-meta"] = encoded
	resolved, err := ResolveNode(context.Background(), node, secrets)
	if err != nil {
		t.Fatal(err)
	}
	xray, err := xrayOutbound(resolved, "XHTTP", w.Settings.Network)
	if err != nil {
		t.Fatal(err)
	}
	stream := xray["streamSettings"].(map[string]any)
	if stream["method"] != "xhttp" {
		t.Fatalf("Xray did not select XHTTP method: %+v", stream)
	}
	settings := stream["xhttpSettings"].(map[string]any)
	if settings["path"] != "/api" || settings["host"] != "cdn.example" || settings["mode"] != "stream-up" || settings["extra"].(map[string]any)["xPaddingBytes"] != "100-1000" {
		t.Fatalf("Xray XHTTP options missing: %+v", settings)
	}
	mihomo, err := mihomoProxy(resolved, "XHTTP", w.Settings.Network)
	if err != nil {
		t.Fatal(err)
	}
	opts := mihomo["xhttp-opts"].(map[string]any)
	if mihomo["network"] != "xhttp" || opts["mode"] != "stream-up" || opts["xPaddingBytes"] != "100-1000" {
		t.Fatalf("Mihomo XHTTP options missing: %+v", mihomo)
	}
	if _, _, err := singBoxOutbound(resolved, "XHTTP", w.Settings.Network); err == nil || !strings.Contains(err.Error(), "does not support Xray XHTTP") {
		t.Fatalf("sing-box should reject unsupported XHTTP explicitly, got %v", err)
	}
}

func TestGenerateWireGuardPreservesReservedAndIPv6Addresses(t *testing.T) {
	w := domain.DefaultWorkspace()
	secrets := adapterSecrets{"wg-private": "private-key"}
	w.Nodes = []domain.Node{{ID: "wg", Name: "WireGuard", Protocol: domain.ProtocolWireGuard, Server: "wg.example", Port: 51820, WGLocalAddress: "10.0.0.2", WGPublicKey: "public-key", Credentials: domain.Credentials{PrivateKeyRef: "wg-private"}, SourceMetadataRef: "wg-meta"}}
	w.ActiveNodeID = "wg"
	encoded, err := security.EncodeMetadataJSON([]byte(`{"extra":{"wg_ipv6_address":"fd00::2","wg_allowed_ips":["0.0.0.0/0"],"wg_reserved":[1,2,3],"wg_mtu":1380,"wg_preshared_key":"psk-secret"}}`))
	if err != nil {
		t.Fatal(err)
	}
	secrets["wg-meta"] = encoded
	generated, err := GenerateConfig(context.Background(), w, "sing-box", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	endpoint := findMap(config["endpoints"].([]any), "CHAIN___base___H1")
	if endpoint == nil {
		t.Fatal("WireGuard endpoint missing")
	}
	addresses := endpoint["address"].([]any)
	if len(addresses) != 2 || addresses[0] != "10.0.0.2/32" || addresses[1] != "fd00::2/128" {
		t.Fatalf("WireGuard addresses not normalized: %+v", addresses)
	}
	peer := endpoint["peers"].([]any)[0].(map[string]any)
	if peer["reserved"] == nil || peer["pre_shared_key"] != "psk-secret" {
		t.Fatalf("WireGuard peer metadata missing: %+v", peer)
	}
}

func TestGenerateXrayRejectsNativeTUNRequest(t *testing.T) {
	w, s := adapterWorkspace()
	w.TUN = domain.TUNBinding{Kind: domain.TUNBindingChain, TargetID: "route", Enabled: true}
	if _, err := GenerateConfig(context.Background(), w, "xray", s); err == nil {
		t.Fatal("Xray native TUN should fail clearly rather than silently ignore the binding")
	}
}

func TestGenerateNativeTUNForSingBoxAndMihomoUsesWholeChain(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.TUN = domain.TUNBinding{Kind: domain.TUNBindingChain, TargetID: "route", Enabled: true}
	for _, coreName := range []string{"sing-box", "mihomo"} {
		t.Run(coreName, func(t *testing.T) {
			generated, err := GenerateConfig(context.Background(), w, coreName, secrets)
			if err != nil {
				t.Fatal(err)
			}
			if coreName == "sing-box" {
				var config map[string]any
				if err := json.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				found := false
				for _, item := range config["inbounds"].([]any) {
					if item.(map[string]any)["tag"] == "IN_TUN" {
						found = true
					}
				}
				if !found {
					t.Fatal("sing-box TUN inbound missing")
				}
				rules := config["route"].(map[string]any)["rules"].([]any)
				found = false
				for _, item := range rules {
					if rule, ok := item.(map[string]any); ok && rule["inbound"] != nil && rule["outbound"] == "CHAIN___tun_chain_route_H2" {
						found = true
					}
				}
				if !found {
					t.Fatalf("sing-box TUN route does not target complete Chain: %s", generated.Data)
				}
			} else {
				var config map[string]any
				if err := yaml.Unmarshal(generated.Data, &config); err != nil {
					t.Fatal(err)
				}
				if config["tun"].(map[string]any)["enable"] != true {
					t.Fatal("Mihomo TUN is not enabled")
				}
				rules := config["rules"].([]any)
				last := rules[len(rules)-1].(string)
				if !strings.Contains(last, "CHAIN___tun_chain_route_H2") {
					t.Fatalf("Mihomo TUN final rule does not target complete Chain: %s", generated.Data)
				}
			}
		})
	}
}

func TestXrayFinalFragmentUsesFinalOutboundDialer(t *testing.T) {
	w, secrets := adapterWorkspace()
	w.Settings.Network.EnableFinalFragment = true
	generated, err := GenerateConfig(context.Background(), w, "xray", secrets)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(generated.Data, &config); err != nil {
		t.Fatal(err)
	}
	outbounds := config["outbounds"].([]any)
	fragment := findMap(outbounds, "CHAIN_route_FINAL_FRAGMENT")
	if fragment == nil {
		t.Fatal("final fragment outbound missing")
	}
	stream := fragment["streamSettings"].(map[string]any)
	sock := stream["sockopt"].(map[string]any)
	if sock["dialerProxy"] != "CHAIN_route_H2" {
		t.Fatalf("final fragment is not chained after route exit: %+v", sock)
	}
}

func TestGenerateConfigFailsClosedWhenCredentialVaultUnavailable(t *testing.T) {
	w, _ := adapterWorkspace()
	if _, err := GenerateConfig(context.Background(), w, "sing-box", nil); !errors.Is(err, security.ErrUnavailable) {
		t.Fatalf("expected credential vault error, got %v", err)
	}
}

func findMap(items []any, tag string) map[string]any {
	for _, item := range items {
		if value, ok := item.(map[string]any); ok && value["tag"] == tag || ok && value["name"] == tag {
			return value
		}
	}
	return nil
}
