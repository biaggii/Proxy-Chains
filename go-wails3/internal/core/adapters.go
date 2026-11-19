package core

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/url"
	"runtime"
	"sort"
	"strconv"
	"strings"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
	"gopkg.in/yaml.v3"
)

type GeneratedConfig struct {
	Core      string
	Extension string
	Data      []byte
}

type chainRoute struct {
	ID       string
	Hops     []ResolvedNode
	FinalTag string
}

func GenerateConfig(ctx context.Context, workspace domain.Workspace, coreName string, secrets security.SecretStore) (GeneratedConfig, error) {
	if err := workspace.Validate(); err != nil {
		return GeneratedConfig{}, err
	}
	switch strings.ToLower(coreName) {
	case "sing-box", "singbox":
		data, err := generateSingBox(ctx, workspace, secrets)
		return GeneratedConfig{Core: "sing-box", Extension: ".json", Data: data}, err
	case "xray":
		data, err := generateXray(ctx, workspace, secrets)
		return GeneratedConfig{Core: "xray", Extension: ".json", Data: data}, err
	case "mihomo", "clash-meta":
		data, err := generateMihomo(ctx, workspace, secrets)
		return GeneratedConfig{Core: "mihomo", Extension: ".yaml", Data: data}, err
	default:
		return GeneratedConfig{}, fmt.Errorf("unsupported core %q", coreName)
	}
}

func collectRoutes(ctx context.Context, w domain.Workspace, secrets security.SecretStore) ([]chainRoute, error) {
	ids := []string{}
	if w.ActiveNodeID != "" {
		ids = append(ids, "__base__")
	}
	for _, binding := range w.PortBindings {
		ids = append(ids, binding.ChainID)
	}
	if w.TUN.Enabled {
		if w.TUN.Kind == domain.TUNBindingNode {
			ids = append(ids, "__tun_base__")
		} else if w.TUN.Kind == domain.TUNBindingChain {
			ids = append(ids, "__tun_chain__")
		}
	}
	seen := map[string]bool{}
	var routes []chainRoute
	for _, id := range ids {
		if seen[id] {
			continue
		}
		seen[id] = true
		var nodeIDs []string
		switch id {
		case "__base__", "__tun_base__":
			nodeIDs = []string{w.ActiveNodeID}
			if id == "__tun_base__" {
				nodeIDs = []string{w.TUN.TargetID}
			}
		case "__tun_chain__":
			for _, chain := range w.Chains {
				if chain.ID == w.TUN.TargetID {
					nodeIDs = chain.HopNodeIDs
					break
				}
			}
		default:
			for _, chain := range w.Chains {
				if chain.ID == id {
					nodeIDs = chain.HopNodeIDs
					break
				}
			}
		}
		if len(nodeIDs) == 0 {
			return nil, fmt.Errorf("route %q has no hops", id)
		}
		routeID := id
		if id == "__tun_base__" {
			routeID = "__tun_base_node__"
		}
		if id == "__tun_chain__" {
			routeID = "__tun_chain_" + w.TUN.TargetID
		}
		route := chainRoute{ID: routeID}
		for _, nodeID := range nodeIDs {
			var node *domain.Node
			for i := range w.Nodes {
				if w.Nodes[i].ID == nodeID {
					node = &w.Nodes[i]
					break
				}
			}
			if node == nil {
				return nil, fmt.Errorf("route %q references missing node %q", id, nodeID)
			}
			resolved, err := ResolveNode(ctx, *node, secrets)
			if err != nil {
				return nil, fmt.Errorf("resolve credentials for node %q: %w", node.Name, err)
			}
			route.Hops = append(route.Hops, resolved)
		}
		route.FinalTag = routeTag(route.ID, len(route.Hops))
		routes = append(routes, route)
	}
	return routes, nil
}

func routeTag(id string, hop int) string { return fmt.Sprintf("CHAIN_%s_H%d", safeTag(id), hop) }
func safeTag(value string) string {
	value = strings.ReplaceAll(value, "-", "_")
	value = strings.ReplaceAll(value, " ", "_")
	return value
}

func generateSingBox(ctx context.Context, w domain.Workspace, secrets security.SecretStore) ([]byte, error) {
	routes, err := collectRoutes(ctx, w, secrets)
	if err != nil {
		return nil, err
	}
	outbounds := []any{map[string]any{"type": "direct", "tag": "DIRECT"}, map[string]any{"type": "block", "tag": "BLOCK"}}
	endpoints := []any{}
	finalByID := map[string]string{}
	for _, route := range routes {
		if routeHasTCPOnlyUpstream(route) && wireguardAfterFirst(route) {
			return nil, fmt.Errorf("WireGuard cannot be chained after a local TCP-only SOCKS upstream")
		}
		for i, node := range route.Hops {
			tag := routeTag(route.ID, i+1)
			ob, endpoint, err := singBoxOutbound(node, tag, w.Settings.Network)
			if err != nil {
				return nil, err
			}
			if i > 0 {
				prev := routeTag(route.ID, i)
				if endpoint {
					ob["detour"] = prev
				} else {
					ob["detour"] = prev
				}
			}
			if endpoint {
				endpoints = append(endpoints, ob)
			} else {
				outbounds = append(outbounds, ob)
			}
		}
		finalByID[route.ID] = route.FinalTag
	}
	inbounds := []any{}
	rules := []any{}
	if w.ActiveNodeID != "" {
		inbounds = append(inbounds, map[string]any{"type": "mixed", "tag": "IN_BASE", "listen": w.Settings.BaseListenHost, "listen_port": w.Settings.BaseListenPort})
		rules = append(rules, map[string]any{"inbound": []string{"IN_BASE"}, "outbound": finalByID["__base__"]})
	}
	for _, binding := range w.PortBindings {
		tag := fmt.Sprintf("IN_%d", binding.ListenPort)
		inbounds = append(inbounds, map[string]any{"type": "mixed", "tag": tag, "listen": binding.ListenHost, "listen_port": binding.ListenPort})
		rules = append(rules, map[string]any{"inbound": []string{tag}, "outbound": finalByID[binding.ChainID]})
	}
	if !w.Settings.Network.EnableIPv6 {
		rules = append([]any{map[string]any{"ip_version": 6, "action": "reject"}}, rules...)
	}
	if w.TUN.Enabled {
		tunInbound := map[string]any{"type": "tun", "tag": "IN_TUN", "address": []string{"172.19.0.1/30"}, "auto_route": true, "strict_route": true, "dns_mode": "hijack"}
		if runtime.GOOS == "linux" {
			tunInbound["interface_name"] = "chainport-tun"
			tunInbound["auto_redirect"] = true
		} else if runtime.GOOS == "windows" {
			tunInbound["interface_name"] = "chainport-tun"
		}
		inbounds = append(inbounds, tunInbound)
		target := finalByID["__tun_base_node__"]
		if target == "" {
			target = finalByID["__tun_chain_"+w.TUN.TargetID]
		}
		if target == "" {
			return nil, fmt.Errorf("TUN target route is missing")
		}
		rules = append([]any{
			map[string]any{"inbound": []string{"IN_TUN"}, "process_name": []string{"sing-box", "xray", "mihomo", "chainport", "python", "pythonw"}, "outbound": "DIRECT"},
			map[string]any{"inbound": []string{"IN_TUN"}, "outbound": target},
		}, rules...)
	}
	frontRules := []any{}
	if w.Settings.Network.EnableSniffing {
		frontRules = append(frontRules,
			map[string]any{"action": "sniff"},
			map[string]any{"type": "logical", "mode": "or", "rules": []any{map[string]any{"port": []int{53}}, map[string]any{"protocol": []string{"dns"}}}, "action": "hijack-dns"},
		)
	} else {
		frontRules = append(frontRules, map[string]any{"port": []int{53}, "action": "hijack-dns"})
	}
	if w.Settings.Network.EnableFinalFragment {
		fragmentRule := map[string]any{"action": "route-options", "tls_record_fragment": true}
		if w.Settings.Network.EnableSniffing {
			fragmentRule["protocol"] = []string{"tls"}
		}
		frontRules = append(frontRules, fragmentRule)
	}
	// Keep local destinations local for every mixed inbound, including normal
	// browser/system-proxy traffic when TUN is disabled. 0.0.0.0/8 is included
	// because local dashboard links sometimes use the wildcard bind address;
	// clients should normally connect through 127.0.0.1 or localhost.
	frontRules = append(frontRules,
		map[string]any{"domain_suffix": []string{"localhost"}, "outbound": "DIRECT"},
		map[string]any{"ip_cidr": []string{"0.0.0.0/8", "127.0.0.0/8", "::/128", "::1/128"}, "outbound": "DIRECT"},
		map[string]any{"ip_is_private": true, "outbound": "DIRECT"},
	)
	if w.Settings.Network.BlockQUIC {
		frontRules = append(frontRules, map[string]any{"network": []string{"udp"}, "port": []int{443}, "action": "reject"})
	}
	rules = append(frontRules, rules...)
	remoteDNS, err := url.Parse(w.Settings.Network.RemoteDNSURL)
	if err != nil || remoteDNS.Scheme != "https" || remoteDNS.Host == "" {
		return nil, fmt.Errorf("remote DNS must be a valid HTTPS URL")
	}
	dnsServers := []any{
		map[string]any{"tag": "local_dns", "type": "udp", "server": w.Settings.Network.BootstrapDNS},
		map[string]any{"tag": "direct_dns", "type": "udp", "server": w.Settings.Network.BootstrapDNS, "domain_resolver": "local_dns"},
		map[string]any{"tag": "hosts_dns", "type": "hosts", "predefined": dnsBootstrapHosts()},
	}
	dnsRules := []any{map[string]any{"server": "hosts_dns", "preferred_by": "hosts_dns"}}
	remoteTagByRoute := map[string]string{}
	for _, route := range routes {
		remoteTag := "remote_dns_" + safeTag(route.ID)
		remoteTagByRoute[route.ID] = remoteTag
		dnsServers = append(dnsServers, map[string]any{"tag": remoteTag, "type": "https", "server": remoteDNS.Hostname(), "server_port": remotePort(remoteDNS), "path": remoteDNSPath(remoteDNS), "domain_resolver": "hosts_dns", "detour": route.FinalTag})
		inboundTags := []string{}
		if route.ID == "__base__" {
			inboundTags = append(inboundTags, "IN_BASE")
		}
		if strings.HasPrefix(route.ID, "__tun_") {
			inboundTags = append(inboundTags, "IN_TUN")
		}
		for _, binding := range w.PortBindings {
			if binding.ChainID == route.ID {
				inboundTags = append(inboundTags, fmt.Sprintf("IN_%d", binding.ListenPort))
			}
		}
		if len(inboundTags) > 0 {
			dnsRules = append(dnsRules, map[string]any{"inbound": inboundTags, "action": "route", "server": remoteTag})
		}
	}
	finalDNS := "local_dns"
	if w.TUN.Enabled {
		if tag := remoteTagByRoute["__tun_base_node__"]; tag != "" {
			finalDNS = tag
		} else if tag := remoteTagByRoute["__tun_chain_"+w.TUN.TargetID]; tag != "" {
			finalDNS = tag
		}
	}
	if finalDNS == "local_dns" {
		if tag := remoteTagByRoute["__base__"]; tag != "" {
			finalDNS = tag
		} else if len(w.PortBindings) > 0 {
			finalDNS = remoteTagByRoute[w.PortBindings[0].ChainID]
		}
	}
	dnsStrategy := "prefer_ipv4"
	if !w.Settings.Network.EnableIPv6 {
		dnsStrategy = "ipv4_only"
	}
	dns := map[string]any{"servers": dnsServers, "rules": dnsRules, "final": finalDNS, "strategy": dnsStrategy}
	defaultResolver := map[string]any{"server": "direct_dns", "strategy": dnsStrategy}
	config := map[string]any{"log": map[string]any{"level": normalizeLogLevel("sing-box", w.Settings.Core.LogLevel), "timestamp": true}, "dns": dns, "inbounds": inbounds, "outbounds": outbounds, "endpoints": endpoints, "route": map[string]any{"rules": rules, "final": "DIRECT", "auto_detect_interface": w.TUN.Enabled, "default_domain_resolver": defaultResolver}}
	return json.MarshalIndent(config, "", "  ")
}

func remotePort(remoteDNS *url.URL) int {
	if remoteDNS.Port() != "" {
		if port, err := strconv.Atoi(remoteDNS.Port()); err == nil {
			return port
		}
	}
	return 443
}

func remoteDNSPath(remoteDNS *url.URL) string {
	path := remoteDNS.EscapedPath()
	if path == "" {
		path = "/dns-query"
	}
	if remoteDNS.RawQuery != "" {
		path += "?" + remoteDNS.RawQuery
	}
	return path
}

func normalizeLogLevel(coreName, level string) string {
	level = strings.ToLower(strings.TrimSpace(level))
	switch coreName {
	case "sing-box":
		if level == "warning" {
			return "warn"
		}
	case "xray":
		if level == "trace" {
			return "debug"
		}
		if level == "warn" {
			return "warning"
		}
	case "mihomo":
		if level == "trace" || level == "fatal" {
			return "debug"
		}
		if level == "warn" {
			return "warning"
		}
	}
	if level == "" {
		return "warning"
	}
	return level
}

func dnsBootstrapHosts() map[string]any {
	return map[string]any{
		"dns.google":                       []string{"8.8.8.8", "8.8.4.4", "2001:4860:4860::8888", "2001:4860:4860::8844"},
		"dns.alidns.com":                   []string{"223.5.5.5", "223.6.6.6", "2400:3200::1", "2400:3200:baba::1"},
		"one.one.one.one":                  []string{"1.1.1.1", "1.0.0.1", "2606:4700:4700::1111", "2606:4700:4700::1001"},
		"1dot1dot1dot1.cloudflare-dns.com": []string{"1.1.1.1", "1.0.0.1", "2606:4700:4700::1111", "2606:4700:4700::1001"},
		"cloudflare-dns.com":               []string{"104.16.249.249", "104.16.248.249", "2606:4700::6810:f8f9", "2606:4700::6810:f9f9"},
		"dns.cloudflare.com":               []string{"162.159.61.8", "172.64.41.8", "2a06:98c1:52::8", "2803:f800:53::8"},
		"dot.pub":                          []string{"1.12.12.12", "120.53.53.53"}, "doh.pub": []string{"1.12.12.12", "120.53.53.53"},
		"dns.quad9.net":               []string{"9.9.9.9", "149.112.112.112", "2620:fe::fe", "2620:fe::9"},
		"dns.yandex.net":              []string{"77.88.8.8", "77.88.8.1", "2a02:6b8::feed:0ff", "2a02:6b8:0:1::feed:0ff"},
		"dns.sb":                      []string{"45.11.45.11", "185.222.222.222", "2a09::", "2a11::"},
		"dns.umbrella.com":            []string{"208.67.220.220", "208.67.222.222", "2620:119:35::35", "2620:119:53::53"},
		"dns.sse.cisco.com":           []string{"208.67.220.220", "208.67.222.222", "2620:119:35::35", "2620:119:53::53"},
		"engage.cloudflareclient.com": []string{"162.159.192.1", "2606:4700:d0::a29f:c001"},
	}
}

func singBoxOutbound(n ResolvedNode, tag string, network domain.NetworkSettings) (map[string]any, bool, error) {
	d := n.Domain
	if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && (d.Transport.Network != "" && d.Transport.Network != "tcp" && d.Transport.Network != "raw") {
		return nil, false, fmt.Errorf("sing-box VLESS flow %q requires RAW/TCP transport", d.Flow)
	}
	ob := map[string]any{"tag": tag, "server": d.Server, "server_port": d.Port, "connect_timeout": "10s"}
	switch d.Protocol {
	case domain.ProtocolVMess:
		ob["type"], ob["uuid"], ob["alter_id"], ob["security"] = "vmess", n.UUID, d.AlterID, defaultString(d.Security, defaultString(d.Cipher, "auto"))
	case domain.ProtocolVLESS:
		ob["type"], ob["uuid"], ob["packet_encoding"] = "vless", n.UUID, "xudp"
		if d.Flow != "" {
			if !d.TLS.Enabled {
				return nil, false, fmt.Errorf("VLESS flow %q requires TLS or REALITY", d.Flow)
			}
			ob["flow"] = d.Flow
		}
	case domain.ProtocolTrojan:
		ob["type"], ob["password"] = "trojan", n.Password
	case domain.ProtocolShadowsocks:
		ob["type"], ob["method"], ob["password"] = "shadowsocks", defaultString(d.Cipher, "aes-256-gcm"), n.Password
	case domain.ProtocolSOCKS5:
		ob["type"], ob["version"] = "socks", "5"
		if n.Username != "" {
			ob["username"] = n.Username
		}
		if n.Password != "" {
			ob["password"] = n.Password
		}
	case domain.ProtocolHTTP:
		ob["type"] = "http"
		if n.Username != "" {
			ob["username"] = n.Username
		}
		if n.Password != "" {
			ob["password"] = n.Password
		}
	case domain.ProtocolWireGuard:
		if !network.EnableUDP {
			return nil, false, fmt.Errorf("WireGuard requires UDP forwarding to be enabled")
		}
		allowedIPs := extraStringSlice(n.Extra, "wg_allowed_ips", "allowed_ips", "allowed-ips")
		if len(allowedIPs) == 0 {
			allowedIPs = []string{"0.0.0.0/0"}
			if network.EnableIPv6 {
				allowedIPs = append(allowedIPs, "::/0")
			}
		}
		peer := map[string]any{"address": d.Server, "port": d.Port, "public_key": d.WGPublicKey, "allowed_ips": allowedIPs}
		if value := extraString(n.Extra, "preshared_key", "wg_preshared_key", "preshared-key"); value != "" {
			peer["pre_shared_key"] = value
		}
		if reserved := extraIntSlice(n.Extra, "wg_reserved", "reserved"); len(reserved) > 0 {
			peer["reserved"] = reserved
		}
		if keepalive := extraInt(n.Extra, "persistent-keepalive", "keepalive"); keepalive > 0 {
			peer["persistent_keepalive_interval"] = keepalive
		}
		addresses := []string{}
		if d.WGLocalAddress != "" {
			addresses = append(addresses, wireguardPrefix(d.WGLocalAddress))
		}
		if ipv6 := extraString(n.Extra, "wg_ipv6_address", "ipv6"); ipv6 != "" {
			addresses = append(addresses, wireguardPrefix(ipv6))
		}
		if len(addresses) == 0 {
			addresses = []string{"172.16.0.2/32"}
		}
		endpoint := map[string]any{"type": "wireguard", "tag": tag, "address": addresses, "private_key": n.PrivateKey, "peers": []any{peer}}
		if mtu := extraInt(n.Extra, "wg_mtu", "wg-mtu", "mtu"); mtu > 0 {
			endpoint["mtu"] = mtu
		}
		return endpoint, true, nil
	default:
		return nil, false, fmt.Errorf("sing-box does not support node protocol %q", d.Protocol)
	}
	if d.TLS.Enabled {
		tls := map[string]any{"enabled": true, "insecure": d.TLS.Insecure || network.AllowInsecure}
		if d.TLS.SNI != "" {
			tls["server_name"] = d.TLS.SNI
		}
		if len(d.TLS.ALPN) > 0 {
			tls["alpn"] = d.TLS.ALPN
		} else if d.Transport.Network == "ws" || d.Transport.Network == "httpupgrade" {
			tls["alpn"] = []string{"http/1.1"}
		} else if d.Transport.Network == "h2" || d.Transport.Network == "http" {
			tls["alpn"] = []string{"h2"}
		}
		if fingerprint := nodeParam(n.Extra, "fp"); fingerprint != "" {
			tls["utls"] = map[string]any{"enabled": true, "fingerprint": fingerprint}
		}
		if nodeParam(n.Extra, "security") == "reality" {
			key := nodeParam(n.Extra, "pbk")
			if key == "" {
				return nil, false, fmt.Errorf("sing-box REALITY requires the server public key (pbk)")
			}
			reality := map[string]any{"enabled": true, "public_key": key}
			if shortID := nodeParam(n.Extra, "sid"); shortID != "" {
				reality["short_id"] = shortID
			}
			tls["reality"] = reality
		}
		if network.EnableFragment && (d.Protocol == domain.ProtocolVMess || d.Protocol == domain.ProtocolVLESS || d.Protocol == domain.ProtocolTrojan) {
			tls["fragment"] = true
			tls["record_fragment"] = true
		}
		ob["tls"] = tls
	}
	if d.Transport.Network == "ws" {
		tr := map[string]any{"type": "ws"}
		if d.Transport.Path != "" {
			tr["path"] = d.Transport.Path
		}
		if d.Transport.Host != "" {
			tr["headers"] = map[string]string{"Host": d.Transport.Host}
		}
		ob["transport"] = tr
	} else if d.Transport.Network == "grpc" {
		tr := map[string]any{"type": "grpc"}
		if d.Transport.Path != "" {
			tr["service_name"] = d.Transport.Path
		}
		ob["transport"] = tr
	} else if d.Transport.Network == "h2" || d.Transport.Network == "http" {
		tr := map[string]any{"type": "http"}
		if d.Transport.Path != "" {
			tr["path"] = d.Transport.Path
		}
		if d.Transport.Host != "" {
			tr["host"] = []string{d.Transport.Host}
		}
		ob["transport"] = tr
	} else if d.Transport.Network == "httpupgrade" {
		tr := map[string]any{"type": "httpupgrade"}
		if d.Transport.Path != "" {
			tr["path"] = d.Transport.Path
		}
		if d.Transport.Host != "" {
			tr["host"] = d.Transport.Host
		}
		ob["transport"] = tr
	} else if d.Transport.Network == "xhttp" {
		return nil, false, fmt.Errorf("sing-box does not support Xray XHTTP transport; select Xray or Mihomo for this node")
	} else if d.Transport.Network != "" && d.Transport.Network != "tcp" && d.Transport.Network != "raw" {
		return nil, false, fmt.Errorf("sing-box transport %q is not supported by this adapter", d.Transport.Network)
	}
	if plugin := extraString(n.Extra, "plugin"); plugin != "" {
		pluginName := plugin
		if pluginName == "obfs" {
			pluginName = "obfs-local"
		}
		ob["plugin"] = pluginName
		if options, ok := n.Extra["plugin_opts"]; ok {
			ob["plugin_opts"] = pluginOptionsString(options)
		}
	}
	if network.EnableMux && (d.Protocol == domain.ProtocolVMess || d.Protocol == domain.ProtocolVLESS || d.Protocol == domain.ProtocolTrojan || d.Protocol == domain.ProtocolShadowsocks) {
		ob["multiplex"] = map[string]any{"enabled": true, "protocol": defaultString(network.SingboxMuxProtocol, "h2mux")}
	}
	return ob, false, nil
}

func generateXray(ctx context.Context, w domain.Workspace, secrets security.SecretStore) ([]byte, error) {
	routes, err := collectRoutes(ctx, w, secrets)
	if err != nil {
		return nil, err
	}
	outbounds := []any{map[string]any{"protocol": "freedom", "tag": "DIRECT", "settings": map[string]any{}}, map[string]any{"protocol": "blackhole", "tag": "BLOCK", "settings": map[string]any{}}}
	finalByID := map[string]string{}
	for _, route := range routes {
		if routeHasTCPOnlyUpstream(route) && wireguardAfterFirst(route) {
			return nil, fmt.Errorf("WireGuard cannot be chained after a local TCP-only SOCKS upstream")
		}
		finalTag := route.FinalTag
		for i, node := range route.Hops {
			if i > 0 && node.Domain.Protocol == domain.ProtocolWireGuard {
				return nil, fmt.Errorf("Xray cannot place a WireGuard outbound after another Chain hop; place WireGuard first or use sing-box/Mihomo")
			}
			tag := routeTag(route.ID, i+1)
			ob, err := xrayOutbound(node, tag, w.Settings.Network)
			if err != nil {
				return nil, err
			}
			if i > 0 {
				stream := mapValue(ob["streamSettings"])
				if stream == nil {
					stream = map[string]any{"method": "raw"}
					ob["streamSettings"] = stream
				}
				sock := mapValue(stream["sockopt"])
				if sock == nil {
					sock = map[string]any{}
					stream["sockopt"] = sock
				}
				sock["dialerProxy"] = routeTag(route.ID, i)
			}
			if i == 0 && w.Settings.Network.EnableFragment {
				stream := mapValue(ob["streamSettings"])
				if stream != nil && stream["security"] != "" {
					mask := xrayFragmentMask(w.Settings.Network)
					if stream["security"] == "reality" && mask["settings"].(map[string]any)["packets"] == "tlshello" {
						mask["settings"].(map[string]any)["packets"] = "1-3"
					}
					stream["finalmask"] = map[string]any{"tcp": []any{mask}}
					ob["streamSettings"] = stream
				}
			}
			outbounds = append(outbounds, ob)
		}
		if w.Settings.Network.EnableFinalFragment {
			fragmentTag := "CHAIN_" + safeTag(route.ID) + "_FINAL_FRAGMENT"
			outbounds = append(outbounds, map[string]any{"protocol": "freedom", "tag": fragmentTag, "settings": map[string]any{}, "streamSettings": map[string]any{"method": "raw", "finalmask": map[string]any{"tcp": []any{xrayFragmentMask(w.Settings.Network)}}, "sockopt": map[string]any{"dialerProxy": finalTag}}})
			finalTag = fragmentTag
		}
		finalByID[route.ID] = finalTag
	}
	inbounds := []any{}
	rules := []any{}
	if w.ActiveNodeID != "" {
		inbounds = append(inbounds, map[string]any{"listen": w.Settings.BaseListenHost, "port": w.Settings.BaseListenPort, "protocol": "socks", "tag": "IN_BASE", "settings": map[string]any{"auth": "noauth", "udp": w.Settings.Network.EnableUDP}, "sniffing": map[string]any{"enabled": w.Settings.Network.EnableSniffing, "destOverride": []string{"http", "tls"}}})
		rules = append(rules, map[string]any{"type": "field", "inboundTag": []string{"IN_BASE"}, "outboundTag": finalByID["__base__"]})
	}
	for _, binding := range w.PortBindings {
		tag := fmt.Sprintf("IN_%d", binding.ListenPort)
		inbounds = append(inbounds, map[string]any{"listen": binding.ListenHost, "port": binding.ListenPort, "protocol": "socks", "tag": tag, "settings": map[string]any{"auth": "noauth", "udp": w.Settings.Network.EnableUDP}})
		rules = append(rules, map[string]any{"type": "field", "inboundTag": []string{tag}, "outboundTag": finalByID[binding.ChainID]})
	}
	if w.TUN.Enabled {
		return nil, fmt.Errorf("Xray TUN interface requires the external TUN bridge; select sing-box or Mihomo for native TUN")
	}
	// Route local hostnames and private/loopback destinations directly before
	// the per-inbound Chain rules. This keeps localhost services reachable
	// while the browser uses ChainPort's local proxy listener.
	localRules := []any{
		map[string]any{"type": "field", "domain": []string{"full:localhost"}, "outboundTag": "DIRECT"},
		map[string]any{"type": "field", "ip": []string{"0.0.0.0/8", "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "224.0.0.0/4", "255.255.255.255/32", "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8"}, "outboundTag": "DIRECT"},
	}
	if !w.Settings.Network.EnableIPv6 {
		localRules = append(localRules, map[string]any{"type": "field", "ip": []string{"::/0"}, "outboundTag": "BLOCK"})
	}
	if w.Settings.Network.BlockQUIC {
		localRules = append(localRules, map[string]any{"type": "field", "network": "udp", "port": "443", "outboundTag": "BLOCK"})
	}
	rules = append(localRules, rules...)
	dnsConfig, err := xrayDNSConfig(w)
	if err != nil {
		return nil, err
	}
	dnsOutbound := "DIRECT"
	if w.TUN.Enabled {
		if value := finalByID["__tun_base_node__"]; value != "" {
			dnsOutbound = value
		} else if value := finalByID["__tun_chain_"+w.TUN.TargetID]; value != "" {
			dnsOutbound = value
		}
	}
	if dnsOutbound == "DIRECT" {
		if value := finalByID["__base__"]; value != "" {
			dnsOutbound = value
		} else if len(w.PortBindings) > 0 {
			dnsOutbound = finalByID[w.PortBindings[0].ChainID]
		}
	}
	rules = append([]any{map[string]any{"type": "field", "inboundTag": []string{"dns-module"}, "outboundTag": dnsOutbound}}, rules...)
	config := map[string]any{"log": map[string]any{"loglevel": normalizeLogLevel("xray", w.Settings.Core.LogLevel)}, "dns": dnsConfig, "inbounds": inbounds, "outbounds": outbounds, "routing": map[string]any{"domainStrategy": "AsIs", "rules": rules}}
	return json.MarshalIndent(config, "", "  ")
}

func xrayFragmentMask(network domain.NetworkSettings) map[string]any {
	packets := defaultString(network.XrayFragmentPackets, "tlshello")
	lengths := network.XrayFragmentLengths
	if len(lengths) == 0 {
		lengths = []string{"50-100"}
	}
	delays := network.XrayFragmentDelays
	if len(delays) == 0 {
		delays = []string{"10-20"}
	}
	return map[string]any{"type": "fragment", "settings": map[string]any{"packets": packets, "lengths": lengths, "delays": delays, "maxSplit": strconv.Itoa(network.XrayFragmentMaxSplit)}}
}

func xrayDNSConfig(w domain.Workspace) (map[string]any, error) {
	remote, err := url.Parse(w.Settings.Network.RemoteDNSURL)
	if err != nil || remote.Scheme != "https" || remote.Host == "" {
		return nil, fmt.Errorf("Xray remote DNS must be a valid HTTPS URL")
	}
	if w.Settings.Network.BootstrapDNS == "" {
		return nil, fmt.Errorf("Xray bootstrap DNS cannot be empty")
	}
	return map[string]any{
		"hosts":         dnsBootstrapHosts(),
		"servers":       []any{map[string]any{"address": w.Settings.Network.BootstrapDNS, "domains": []string{"full:" + remote.Hostname()}, "skipFallback": true}, w.Settings.Network.RemoteDNSURL},
		"queryStrategy": map[bool]string{true: "UseIP", false: "UseIPv4"}[w.Settings.Network.EnableIPv6],
		"tag":           "dns-module",
	}, nil
}

func xrayOutbound(n ResolvedNode, tag string, network domain.NetworkSettings) (map[string]any, error) {
	d := n.Domain
	if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && !d.TLS.Enabled {
		return nil, fmt.Errorf("Xray VLESS flow %q requires TLS or REALITY", d.Flow)
	}
	if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && d.Transport.Network != "" && d.Transport.Network != "tcp" && d.Transport.Network != "raw" {
		return nil, fmt.Errorf("Xray VLESS Vision flow requires RAW/TCP transport")
	}
	ob := map[string]any{"tag": tag}
	switch d.Protocol {
	case domain.ProtocolVMess:
		ob["protocol"] = "vmess"
		ob["settings"] = map[string]any{"vnext": []any{map[string]any{"address": d.Server, "port": d.Port, "users": []any{map[string]any{"id": n.UUID, "alterId": d.AlterID, "security": defaultString(d.Security, defaultString(d.Cipher, "auto"))}}}}}
	case domain.ProtocolVLESS:
		ob["protocol"] = "vless"
		user := map[string]any{"id": n.UUID, "encryption": "none"}
		if d.Flow != "" {
			user["flow"] = d.Flow
		}
		ob["settings"] = map[string]any{"vnext": []any{map[string]any{"address": d.Server, "port": d.Port, "users": []any{user}}}}
	case domain.ProtocolTrojan:
		ob["protocol"] = "trojan"
		ob["settings"] = map[string]any{"servers": []any{map[string]any{"address": d.Server, "port": d.Port, "password": n.Password}}}
	case domain.ProtocolShadowsocks:
		ob["protocol"] = "shadowsocks"
		ob["settings"] = map[string]any{"servers": []any{map[string]any{"address": d.Server, "port": d.Port, "method": defaultString(d.Cipher, "aes-256-gcm"), "password": n.Password}}}
	case domain.ProtocolSOCKS5, domain.ProtocolHTTP:
		protocol := "socks"
		if d.Protocol == domain.ProtocolHTTP {
			protocol = "http"
		}
		server := map[string]any{"address": d.Server, "port": d.Port}
		if n.Username != "" {
			server["users"] = []any{map[string]any{"user": n.Username, "pass": n.Password}}
		}
		ob["protocol"] = protocol
		if protocol == "socks" {
			ob["settings"] = map[string]any{"servers": []any{server}}
		} else {
			ob["settings"] = map[string]any{"servers": []any{server}}
		}
		ob["streamSettings"] = map[string]any{"method": "raw"}
	case domain.ProtocolWireGuard:
		if !network.EnableUDP {
			return nil, fmt.Errorf("WireGuard requires UDP forwarding to be enabled")
		}
		ob["protocol"] = "wireguard"
		addresses := []string{}
		if d.WGLocalAddress != "" {
			addresses = append(addresses, wireguardHostAddress(d.WGLocalAddress))
		}
		if ipv6 := extraString(n.Extra, "wg_ipv6_address", "ipv6"); ipv6 != "" {
			addresses = append(addresses, wireguardHostAddress(ipv6))
		}
		allowedIPs := extraStringSlice(n.Extra, "wg_allowed_ips", "allowed_ips", "allowed-ips")
		if len(allowedIPs) == 0 {
			allowedIPs = []string{"0.0.0.0/0"}
			if network.EnableIPv6 {
				allowedIPs = append(allowedIPs, "::/0")
			}
		}
		peer := map[string]any{"publicKey": d.WGPublicKey, "endpoint": netJoin(d.Server, d.Port), "allowedIPs": allowedIPs}
		if psk := extraString(n.Extra, "preshared_key", "wg_preshared_key", "preshared-key"); psk != "" {
			peer["preSharedKey"] = psk
		}
		settings := map[string]any{"secretKey": n.PrivateKey, "address": addresses, "peers": []any{peer}, "remoteDNS": []string{network.BootstrapDNS}}
		if reserved := extraIntSlice(n.Extra, "wg_reserved", "reserved"); len(reserved) > 0 {
			settings["reserved"] = reserved
		}
		if keepalive := extraInt(n.Extra, "persistent-keepalive", "keepalive"); keepalive > 0 {
			peer["keepAlive"] = keepalive
		}
		if mtu := extraInt(n.Extra, "wg_mtu", "wg-mtu", "mtu"); mtu > 0 {
			settings["mtu"] = mtu
		}
		ob["settings"] = settings
	default:
		return nil, fmt.Errorf("Xray does not support node protocol %q", d.Protocol)
	}
	if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && !d.TLS.Enabled {
		return nil, fmt.Errorf("Xray VLESS flow %q requires TLS or REALITY", d.Flow)
	}
	if network.EnableMux && (d.Protocol == domain.ProtocolVMess || d.Protocol == domain.ProtocolVLESS || d.Protocol == domain.ProtocolTrojan || d.Protocol == domain.ProtocolShadowsocks) {
		ob["mux"] = map[string]any{"enabled": true, "concurrency": 8}
	}
	if d.Protocol != domain.ProtocolWireGuard {
		networkName := strings.ToLower(defaultString(d.Transport.Network, "tcp"))
		switch networkName {
		case "tcp", "raw":
			networkName = "raw"
		case "ws":
			networkName = "websocket"
		case "grpc", "gun":
			networkName = "grpc"
		case "xhttp":
			networkName = "xhttp"
		case "httpupgrade":
			networkName = "httpupgrade"
		case "h2", "http":
			return nil, fmt.Errorf("Xray no longer supports the legacy %q HTTP/2 transport; use WebSocket, gRPC, or a compatible Xray core build", networkName)
		default:
			return nil, fmt.Errorf("Xray transport %q is not supported by this adapter", networkName)
		}
		stream := map[string]any{"method": networkName}
		if d.TLS.Enabled {
			security := "tls"
			if nodeParam(n.Extra, "security") == "reality" {
				security = "reality"
			}
			if security == "reality" && networkName != "raw" && networkName != "grpc" && networkName != "xhttp" {
				return nil, fmt.Errorf("Xray REALITY is only supported with RAW, XHTTP or gRPC transport")
			}
			if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && networkName != "raw" {
				return nil, fmt.Errorf("Xray VLESS Vision flow requires RAW transport")
			}
			stream["security"] = security
			alpn := d.TLS.ALPN
			if len(alpn) == 0 {
				if networkName == "websocket" || networkName == "httpupgrade" {
					alpn = []string{"http/1.1"}
				} else if networkName == "xhttp" {
					alpn = []string{"h2"}
				}
			}
			tls := map[string]any{"allowInsecure": d.TLS.Insecure || network.AllowInsecure}
			if d.TLS.SNI != "" {
				tls["serverName"] = d.TLS.SNI
			}
			if len(alpn) > 0 {
				tls["alpn"] = alpn
			}
			if security == "tls" {
				if fingerprint := nodeParam(n.Extra, "fp"); fingerprint != "" {
					tls["fingerprint"] = fingerprint
				}
				stream["tlsSettings"] = tls
			} else {
				key := nodeParam(n.Extra, "pbk")
				if key == "" {
					return nil, fmt.Errorf("Xray REALITY requires the server public key (pbk)")
				}
				reality := map[string]any{"serverName": defaultString(d.TLS.SNI, d.Server), "fingerprint": defaultString(nodeParam(n.Extra, "fp"), "chrome"), "password": key}
				if shortID := nodeParam(n.Extra, "sid"); shortID != "" {
					reality["shortId"] = shortID
				}
				if spider := nodeParam(n.Extra, "spx"); spider != "" {
					reality["spiderX"] = spider
				}
				stream["realitySettings"] = reality
			}
		}
		if networkName == "websocket" {
			ws := map[string]any{"path": d.Transport.Path}
			if d.Transport.Host != "" {
				ws["headers"] = map[string]string{"Host": d.Transport.Host}
			}
			stream["wsSettings"] = ws
		}
		if networkName == "grpc" {
			stream["grpcSettings"] = map[string]any{"serviceName": d.Transport.Path}
		}
		if networkName == "httpupgrade" {
			upgrade := map[string]any{"path": defaultString(d.Transport.Path, "/")}
			if d.Transport.Host != "" {
				upgrade["host"] = d.Transport.Host
			}
			stream["httpupgradeSettings"] = upgrade
		}
		if networkName == "xhttp" {
			settings := map[string]any{"path": defaultString(d.Transport.Path, "/")}
			if d.Transport.Host != "" {
				settings["host"] = d.Transport.Host
			}
			if opts := mapValue(n.Extra["xhttp_opts"]); len(opts) > 0 {
				if mode := fmt.Sprint(opts["mode"]); mode != "" && mode != "<nil>" {
					settings["mode"] = mode
				}
				if headers := mapValue(opts["headers"]); len(headers) > 0 {
					settings["headers"] = headers
				}
				extra := map[string]any{}
				for key, value := range opts {
					switch key {
					case "path", "host", "mode", "headers":
					default:
						extra[xrayXHTTPFieldName(key)] = value
					}
				}
				if len(extra) > 0 {
					settings["extra"] = extra
				}
			}
			if mode := nodeParam(n.Extra, "mode"); mode != "" {
				switch mode {
				case "auto", "packet-up", "stream-up", "stream-one":
					settings["mode"] = mode
				default:
					return nil, fmt.Errorf("unsupported Xray XHTTP mode %q", mode)
				}
			}
			if headers := mapValue(n.Extra["xhttp_headers"]); len(headers) > 0 {
				settings["headers"] = headers
			}
			if extra, err := xhttpExtraOptions(n.Extra); err != nil {
				return nil, fmt.Errorf("invalid XHTTP extra JSON: %w", err)
			} else if len(extra) > 0 {
				settings["extra"] = extra
			}
			stream["xhttpSettings"] = settings
		}
		ob["streamSettings"] = stream
	}
	return ob, nil
}

func xrayXHTTPFieldName(value string) string {
	mapping := map[string]string{"x-padding-bytes": "xPaddingBytes", "x-padding-obfs-mode": "xPaddingObfsMode", "x-padding-key": "xPaddingKey", "x-padding-header": "xPaddingHeader", "x-padding-placement": "xPaddingPlacement", "x-padding-method": "xPaddingMethod", "no-grpc-header": "noGRPCHeader", "no-sse-header": "noSSEHeader", "sc-max-each-post-bytes": "scMaxEachPostBytes", "sc-min-posts-interval-ms": "scMinPostsIntervalMs", "uplink-http-method": "uplinkHTTPMethod", "session-id-placement": "sessionIDPlacement", "session-id-key": "sessionIDKey", "session-id-table": "sessionIDTable", "session-id-length": "sessionIDLength", "seq-placement": "seqPlacement", "seq-key": "seqKey", "uplink-data-placement": "uplinkDataPlacement", "uplink-data-key": "uplinkDataKey", "uplink-chunk-size": "uplinkChunkSize"}
	if mapped, ok := mapping[value]; ok {
		return mapped
	}
	return value
}

func xhttpExtraOptions(extra map[string]any) (map[string]any, error) {
	if value := extra["extra"]; value != nil {
		switch raw := value.(type) {
		case string:
			var parsed map[string]any
			if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
				return nil, err
			}
			return parsed, nil
		case map[string]any:
			return raw, nil
		}
	}
	if raw := queryValue(extra, "extra"); raw != "" {
		var parsed map[string]any
		if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
			return nil, err
		}
		return parsed, nil
	}
	return nil, nil
}

func generateMihomo(ctx context.Context, w domain.Workspace, secrets security.SecretStore) ([]byte, error) {
	routes, err := collectRoutes(ctx, w, secrets)
	if err != nil {
		return nil, err
	}
	proxies := []any{}
	finalByID := map[string]string{}
	for _, route := range routes {
		if routeHasTCPOnlyUpstream(route) && wireguardAfterFirst(route) {
			return nil, fmt.Errorf("WireGuard cannot be chained after a local TCP-only SOCKS upstream")
		}
		for i, node := range route.Hops {
			proxy, err := mihomoProxy(node, routeTag(route.ID, i+1), w.Settings.Network)
			if err != nil {
				return nil, err
			}
			if i > 0 {
				proxy["dialer-proxy"] = routeTag(route.ID, i)
			}
			proxies = append(proxies, proxy)
		}
		finalByID[route.ID] = route.FinalTag
	}
	listeners := []any{}
	subRules := map[string]any{}
	if w.ActiveNodeID != "" {
		ruleName := "CHAINPORT_BASE"
		listeners = append(listeners, map[string]any{"name": "IN_BASE", "type": "mixed", "listen": w.Settings.BaseListenHost, "port": w.Settings.BaseListenPort, "udp": w.Settings.Network.EnableUDP, "rule": ruleName})
		subRules[ruleName] = mihomoListenerRules(finalByID["__base__"], w.Settings.Network.BlockQUIC)
	}
	for _, binding := range w.PortBindings {
		ruleName := fmt.Sprintf("CHAINPORT_%d", binding.ListenPort)
		listeners = append(listeners, map[string]any{"name": fmt.Sprintf("IN_%d", binding.ListenPort), "type": "mixed", "listen": binding.ListenHost, "port": binding.ListenPort, "udp": w.Settings.Network.EnableUDP, "rule": ruleName})
		subRules[ruleName] = mihomoListenerRules(finalByID[binding.ChainID], w.Settings.Network.BlockQUIC)
	}
	remoteDNS, err := url.Parse(w.Settings.Network.RemoteDNSURL)
	if err != nil || remoteDNS.Scheme != "https" || remoteDNS.Host == "" {
		return nil, fmt.Errorf("Mihomo remote DNS must be a valid HTTPS URL")
	}
	dnsProxy := "DIRECT"
	if w.TUN.Enabled {
		if value := finalByID["__tun_base_node__"]; value != "" {
			dnsProxy = value
		} else if value := finalByID["__tun_chain_"+w.TUN.TargetID]; value != "" {
			dnsProxy = value
		}
	}
	if dnsProxy == "DIRECT" {
		if value := finalByID["__base__"]; value != "" {
			dnsProxy = value
		} else if len(w.PortBindings) > 0 {
			dnsProxy = finalByID[w.PortBindings[0].ChainID]
		}
	}
	remoteDNSForProxy := w.Settings.Network.RemoteDNSURL + "#" + dnsProxy
	config := map[string]any{"ipv6": w.Settings.Network.EnableIPv6, "allow-lan": w.Settings.Network.AllowLAN, "mode": "rule", "log-level": normalizeLogLevel("mihomo", w.Settings.Core.LogLevel), "proxies": proxies, "listeners": listeners, "rules": []string{"MATCH,DIRECT"}, "sub-rules": subRules, "dns": map[string]any{"enable": true, "ipv6": w.Settings.Network.EnableIPv6, "default-nameserver": []string{w.Settings.Network.BootstrapDNS}, "proxy-server-nameserver": []string{w.Settings.Network.BootstrapDNS}, "direct-nameserver": []string{w.Settings.Network.BootstrapDNS}, "nameserver": []string{remoteDNSForProxy}}}
	if w.TUN.Enabled {
		target := finalByID["__tun_base_node__"]
		if target == "" {
			target = finalByID["__tun_chain_"+w.TUN.TargetID]
		}
		tunConfig := map[string]any{"enable": true, "stack": "system", "auto-route": true, "auto-detect-interface": true, "dns-mode": "hijack", "strict-route": true, "dns-hijack": []string{"any:53", "tcp://any:53"}}
		if runtime.GOOS == "darwin" {
			tunConfig["device"] = "utun"
		} else {
			tunConfig["device"] = "chainport-tun"
		}
		if runtime.GOOS == "linux" {
			tunConfig["auto-redirect"] = true
		}
		config["tun"] = tunConfig
		tunRules := mihomoLocalBypassRules()
		if w.Settings.Network.BlockQUIC {
			tunRules = append(tunRules, "AND,((NETWORK,UDP),(DST-PORT,443)),REJECT")
		}
		tunRules = append(tunRules, "PROCESS-NAME,chainport,DIRECT", "PROCESS-NAME,sing-box,DIRECT", "PROCESS-NAME,xray,DIRECT", "PROCESS-NAME,mihomo,DIRECT", "MATCH,"+target)
		config["rules"] = tunRules
	}
	return yaml.Marshal(config)
}

func mihomoLocalBypassRules() []string {
	return []string{
		"DOMAIN-SUFFIX,localhost,DIRECT",
		"IP-CIDR,0.0.0.0/8,DIRECT,no-resolve",
		"IP-CIDR,127.0.0.0/8,DIRECT,no-resolve",
		"IP-CIDR6,::/128,DIRECT,no-resolve",
		"IP-CIDR6,::1/128,DIRECT,no-resolve",
		"IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
		"IP-CIDR,172.16.0.0/12,DIRECT,no-resolve",
		"IP-CIDR,192.168.0.0/16,DIRECT,no-resolve",
		"IP-CIDR,169.254.0.0/16,DIRECT,no-resolve",
		"IP-CIDR6,fc00::/7,DIRECT,no-resolve",
		"IP-CIDR6,fe80::/10,DIRECT,no-resolve",
	}
}

func mihomoListenerRules(finalTag string, blockQUIC bool) []string {
	rules := mihomoLocalBypassRules()
	if blockQUIC {
		rules = append(rules, "AND,((NETWORK,UDP),(DST-PORT,443)),REJECT")
	}
	return append(rules, "MATCH,"+finalTag)
}

func mihomoProxy(n ResolvedNode, name string, network domain.NetworkSettings) (map[string]any, error) {
	d := n.Domain
	if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && !d.TLS.Enabled {
		return nil, fmt.Errorf("Mihomo VLESS flow %q requires TLS or REALITY", d.Flow)
	}
	if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && d.Transport.Network != "" && d.Transport.Network != "tcp" && d.Transport.Network != "raw" {
		return nil, fmt.Errorf("Mihomo VLESS Vision flow requires TCP transport")
	}
	if d.Protocol == domain.ProtocolVLESS && d.Flow != "" && !d.TLS.Enabled {
		return nil, fmt.Errorf("Mihomo VLESS flow %q requires TLS or REALITY", d.Flow)
	}
	p := map[string]any{"name": name, "server": d.Server, "port": d.Port}
	switch d.Protocol {
	case domain.ProtocolVMess:
		p["type"], p["uuid"], p["alterId"], p["cipher"], p["tls"] = "vmess", n.UUID, d.AlterID, defaultString(d.Security, defaultString(d.Cipher, "auto")), d.TLS.Enabled
	case domain.ProtocolVLESS:
		p["type"], p["uuid"], p["tls"] = "vless", n.UUID, d.TLS.Enabled
		if d.Flow != "" {
			p["flow"] = d.Flow
		}
	case domain.ProtocolTrojan:
		p["type"], p["password"], p["sni"] = "trojan", n.Password, defaultString(d.TLS.SNI, d.Server)
	case domain.ProtocolShadowsocks:
		p["type"], p["cipher"], p["password"] = "ss", defaultString(d.Cipher, "aes-256-gcm"), n.Password
		if plugin := extraString(n.Extra, "plugin"); plugin != "" {
			pluginName := plugin
			if pluginName == "obfs-local" {
				pluginName = "obfs"
			}
			p["plugin"] = pluginName
		}
		if options, ok := n.Extra["plugin_opts"]; ok {
			p["plugin-opts"] = options
		}
	case domain.ProtocolWireGuard:
		if !network.EnableUDP {
			return nil, fmt.Errorf("WireGuard requires UDP forwarding to be enabled")
		}
		p["type"], p["ip"], p["public-key"], p["private-key"], p["udp"] = "wireguard", wireguardHostAddress(d.WGLocalAddress), d.WGPublicKey, n.PrivateKey, true
		if value := extraString(n.Extra, "preshared_key", "wg_preshared_key", "preshared-key"); value != "" {
			p["pre-shared-key"] = value
		}
		if value := extraInt(n.Extra, "wg_mtu", "wg-mtu", "mtu"); value > 0 {
			p["mtu"] = value
		}
		values := extraStringSlice(n.Extra, "wg_allowed_ips", "allowed_ips", "allowed-ips")
		if len(values) == 0 {
			values = []string{"0.0.0.0/0"}
			if network.EnableIPv6 {
				values = append(values, "::/0")
			}
		}
		p["allowed-ips"] = values
		if value := extraString(n.Extra, "wg_ipv6_address", "ipv6"); value != "" {
			p["ipv6"] = wireguardHostAddress(value)
		}
		if reserved := extraIntSlice(n.Extra, "wg_reserved", "reserved"); len(reserved) > 0 {
			p["reserved"] = reserved
		}
		if keepalive := extraInt(n.Extra, "persistent-keepalive", "keepalive"); keepalive > 0 {
			p["persistent-keepalive"] = keepalive
		}
		p["remote-dns-resolve"] = true
		p["dns"] = []string{network.BootstrapDNS}
	case domain.ProtocolSOCKS5, domain.ProtocolHTTP:
		protocol := "socks5"
		if d.Protocol == domain.ProtocolHTTP {
			protocol = "http"
		}
		p["type"] = protocol
		if n.Username != "" {
			p["username"] = n.Username
			p["password"] = n.Password
		}
		if d.TLS.Enabled {
			p["tls"] = true
		}
	default:
		return nil, fmt.Errorf("Mihomo does not support node protocol %q", d.Protocol)
	}
	if d.TLS.SNI != "" && d.Protocol != domain.ProtocolTrojan {
		p["servername"] = d.TLS.SNI
	}
	if nodeParam(n.Extra, "security") == "reality" {
		key := nodeParam(n.Extra, "pbk")
		if key == "" {
			return nil, fmt.Errorf("Mihomo REALITY requires the server public key (pbk)")
		}
		p["reality-opts"] = map[string]any{"public-key": key, "short-id": nodeParam(n.Extra, "sid")}
	}
	if (d.TLS.Enabled || d.Protocol == domain.ProtocolTrojan) && (d.TLS.Insecure || network.AllowInsecure) {
		p["skip-cert-verify"] = true
	}
	if fingerprint := nodeParam(n.Extra, "fp"); fingerprint != "" {
		p["client-fingerprint"] = fingerprint
	}
	if len(d.TLS.ALPN) > 0 {
		p["alpn"] = d.TLS.ALPN
	} else if d.TLS.Enabled {
		switch d.Transport.Network {
		case "ws", "httpupgrade":
			p["alpn"] = []string{"http/1.1"}
		case "xhttp":
			p["alpn"] = []string{"h2"}
		}
	}
	if d.Transport.Network == "ws" {
		ws := map[string]any{"path": d.Transport.Path}
		if d.Transport.Host != "" {
			ws["headers"] = map[string]string{"Host": d.Transport.Host}
		}
		p["network"] = "ws"
		p["ws-opts"] = ws
	} else if d.Transport.Network == "grpc" {
		p["network"] = "grpc"
		p["grpc-opts"] = map[string]any{"grpc-service-name": d.Transport.Path}
	} else if d.Transport.Network == "h2" {
		p["network"] = "h2"
		hosts := []string{}
		if d.Transport.Host != "" {
			hosts = append(hosts, d.Transport.Host)
		}
		p["h2-opts"] = map[string]any{"path": d.Transport.Path, "host": hosts}
	} else if d.Transport.Network == "http" {
		p["network"] = "http"
		opts := map[string]any{"path": []string{defaultString(d.Transport.Path, "/")}}
		if d.Transport.Host != "" {
			opts["headers"] = map[string]any{"Host": []string{d.Transport.Host}}
		}
		if saved := mapValue(n.Extra["http_opts"]); len(saved) > 0 {
			for key, value := range saved {
				opts[key] = value
			}
		}
		p["http-opts"] = opts
	} else if d.Transport.Network == "httpupgrade" {
		p["network"] = "ws"
		opts := map[string]any{"path": defaultString(d.Transport.Path, "/"), "v2ray-http-upgrade": true}
		if d.Transport.Host != "" {
			opts["headers"] = map[string]string{"Host": d.Transport.Host}
		}
		p["ws-opts"] = opts
	} else if d.Transport.Network == "xhttp" {
		if d.Protocol != domain.ProtocolVLESS {
			return nil, fmt.Errorf("Mihomo XHTTP transport is supported only for VLESS nodes")
		}
		p["network"] = "xhttp"
		opts := map[string]any{"path": defaultString(d.Transport.Path, "/"), "host": d.Transport.Host}
		if mode := nodeParam(n.Extra, "mode"); mode != "" {
			opts["mode"] = mode
		}
		if saved := mapValue(n.Extra["xhttp_opts"]); len(saved) > 0 {
			for key, value := range saved {
				opts[key] = value
			}
		}
		if extra, err := xhttpExtraOptions(n.Extra); err != nil {
			return nil, fmt.Errorf("invalid XHTTP extra JSON: %w", err)
		} else {
			for key, value := range extra {
				opts[key] = value
			}
		}
		p["xhttp-opts"] = opts
	} else if d.Transport.Network != "" && d.Transport.Network != "tcp" && d.Transport.Network != "raw" {
		return nil, fmt.Errorf("Mihomo transport %q is not supported by this adapter", d.Transport.Network)
	}
	if network.EnableMux && (d.Protocol == domain.ProtocolVMess || d.Protocol == domain.ProtocolVLESS || d.Protocol == domain.ProtocolTrojan) {
		p["smux"] = map[string]any{"enabled": true, "protocol": "h2mux"}
	}
	return p, nil
}

func mapValue(value any) map[string]any {
	if result, ok := value.(map[string]any); ok {
		return result
	}
	return nil
}
func netJoin(host string, port uint16) string {
	if strings.Contains(host, ":") {
		return fmt.Sprintf("[%s]:%d", host, port)
	}
	return fmt.Sprintf("%s:%d", host, port)
}
func defaultString(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func queryValue(extra map[string]any, key string) string {
	query := mapValue(extra["query"])
	if query == nil {
		return ""
	}
	switch value := query[key].(type) {
	case string:
		return value
	case []string:
		if len(value) > 0 {
			return value[0]
		}
	case []any:
		if len(value) > 0 {
			return fmt.Sprint(value[0])
		}
	}
	return ""
}

func nodeParam(extra map[string]any, key string) string {
	if value := queryValue(extra, key); value != "" {
		return value
	}
	return extraString(extra, key)
}

func extraString(extra map[string]any, keys ...string) string {
	for _, key := range keys {
		if value := extra[key]; value != nil && fmt.Sprint(value) != "" {
			return fmt.Sprint(value)
		}
	}
	return ""
}
func extraStringSlice(extra map[string]any, keys ...string) []string {
	for _, key := range keys {
		switch value := extra[key].(type) {
		case []string:
			return value
		case []any:
			out := []string{}
			for _, item := range value {
				out = append(out, fmt.Sprint(item))
			}
			return out
		case string:
			if value != "" {
				return strings.Split(value, ",")
			}
		}
	}
	return nil
}
func extraInt(extra map[string]any, keys ...string) int {
	value := extraString(extra, keys...)
	number, _ := strconv.Atoi(value)
	return number
}
func extraIntSlice(extra map[string]any, keys ...string) []int {
	for _, key := range keys {
		switch value := extra[key].(type) {
		case []int:
			return value
		case []any:
			out := []int{}
			for _, item := range value {
				number, _ := strconv.Atoi(fmt.Sprint(item))
				out = append(out, number)
			}
			return out
		case string:
			parts := strings.Split(value, ",")
			out := []int{}
			for _, part := range parts {
				number, err := strconv.Atoi(strings.TrimSpace(part))
				if err == nil {
					out = append(out, number)
				}
			}
			return out
		}
	}
	return nil
}
func pluginOptionsString(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	options, ok := value.(map[string]any)
	if !ok {
		return ""
	}
	keys := make([]string, 0, len(options))
	for key := range options {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := []string{}
	for _, key := range keys {
		switch item := options[key].(type) {
		case bool:
			if item {
				parts = append(parts, key)
			}
		default:
			parts = append(parts, key+"="+fmt.Sprint(item))
		}
	}
	return strings.Join(parts, ";")
}
func wireguardPrefix(value string) string {
	value = strings.TrimSpace(value)
	if strings.Contains(value, "/") {
		return value
	}
	if ip := net.ParseIP(value); ip != nil {
		if ip.To4() != nil {
			return value + "/32"
		}
		return value + "/128"
	}
	return value
}
func wireguardHostAddress(value string) string {
	value = strings.TrimSpace(value)
	if index := strings.IndexByte(value, '/'); index >= 0 {
		return value[:index]
	}
	return value
}
func containsProtocol(route chainRoute, protocol domain.Protocol) bool {
	for _, node := range route.Hops {
		if node.Domain.Protocol == protocol {
			return true
		}
	}
	return false
}
func routeHasTCPOnlyUpstream(route chainRoute) bool {
	if len(route.Hops) == 0 || route.Hops[0].Domain.Protocol != domain.ProtocolSOCKS5 {
		return false
	}
	host := strings.Trim(strings.ToLower(route.Hops[0].Domain.Server), "[]")
	if host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func wireguardAfterFirst(route chainRoute) bool {
	if len(route.Hops) < 2 {
		return false
	}
	for _, node := range route.Hops[1:] {
		if node.Domain.Protocol == domain.ProtocolWireGuard {
			return true
		}
	}
	return false
}
