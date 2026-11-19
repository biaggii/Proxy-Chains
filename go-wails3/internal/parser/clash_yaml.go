package parser

import (
	"context"
	"fmt"
	"strings"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"gopkg.in/yaml.v3"
)

func ParseClashYAML(ctx context.Context, text, sourceID string, secrets NodeSecretWriter) ([]domain.Node, []error) {
	var document map[string]any
	if err := yaml.Unmarshal([]byte(text), &document); err != nil {
		return nil, []error{fmt.Errorf("parse Clash YAML: %w", err)}
	}
	proxies, ok := document["proxies"].([]any)
	if !ok {
		return nil, []error{fmt.Errorf("Clash YAML must contain a proxies array")}
	}
	var nodes []domain.Node
	var errs []error
	for index, item := range proxies {
		fields, ok := item.(map[string]any)
		if !ok {
			errs = append(errs, fmt.Errorf("proxy %d is not an object", index+1))
			continue
		}
		parsed, err := parseClashProxy(fields)
		if err != nil {
			errs = append(errs, fmt.Errorf("proxy %d (%s): %w", index+1, valueString(fields["name"]), err))
			continue
		}
		node, err := persistParsedNode(ctx, parsed, sourceID, secrets)
		if err != nil {
			errs = append(errs, fmt.Errorf("proxy %d (%s): %w", index+1, parsed.Name, err))
			continue
		}
		nodes = append(nodes, node)
	}
	return nodes, errs
}

func parseClashProxy(fields map[string]any) (parsedNode, error) {
	name := strings.TrimSpace(valueString(fields["name"]))
	server := strings.TrimSpace(valueString(fields["server"]))
	port, err := parsePort(fields["port"])
	if err != nil {
		return parsedNode{}, err
	}
	if name == "" || server == "" {
		return parsedNode{}, fmt.Errorf("name and server are required")
	}
	protocol := strings.ToLower(valueString(fields["type"]))
	protocolMap := map[string]domain.Protocol{"vmess": domain.ProtocolVMess, "vless": domain.ProtocolVLESS, "trojan": domain.ProtocolTrojan, "ss": domain.ProtocolShadowsocks, "shadowsocks": domain.ProtocolShadowsocks, "wireguard": domain.ProtocolWireGuard, "wg": domain.ProtocolWireGuard, "socks5": domain.ProtocolSOCKS5, "socks": domain.ProtocolSOCKS5, "http": domain.ProtocolHTTP, "https": domain.ProtocolHTTP}
	kind, exists := protocolMap[protocol]
	if !exists {
		return parsedNode{}, fmt.Errorf("unsupported Clash proxy type %q", protocol)
	}
	transportName := "tcp"
	transport := domain.Transport{}
	if network, ok := fields["network"].(string); ok && network != "" {
		transportName = network
	}
	if network := mapValue(fields["network"]); network != nil {
		transportName = valueString(network["type"])
	}
	if transportName == "" {
		transportName = "tcp"
	}
	if transportName == "gun" {
		transportName = "grpc"
	}
	if ws := mapValue(fields["ws-opts"]); ws != nil {
		if transportName == "tcp" {
			transportName = "ws"
		}
		transport.Path = valueString(ws["path"])
		if headers := mapValue(ws["headers"]); headers != nil {
			transport.Host = valueString(headers["Host"])
		}
	}
	if h2 := mapValue(fields["h2-opts"]); h2 != nil {
		if transportName == "tcp" {
			transportName = "h2"
		}
		transport.Path = valueString(h2["path"])
		hosts := toStringSlice(h2["host"])
		if len(hosts) > 0 {
			transport.Host = hosts[0]
		}
	}
	if grpc := mapValue(fields["grpc-opts"]); grpc != nil {
		if transportName == "" || transportName == "tcp" {
			transportName = "grpc"
		}
		transport.Path = valueString(grpc["grpc-service-name"])
	}
	if httpOpts := mapValue(fields["http-opts"]); httpOpts != nil {
		if transportName == "tcp" {
			transportName = "http"
		}
		paths := toStringSlice(httpOpts["path"])
		path := valueString(httpOpts["path"])
		if len(paths) > 0 {
			path = paths[0]
		}
		transport.Path = firstNonEmpty(path, transport.Path)
		parsedHeaders := mapValue(httpOpts["headers"])
		if parsedHeaders != nil {
			transport.Host = firstNonEmpty(valueString(parsedHeaders["Host"]), transport.Host)
		}
	}
	xhttpOpts := mapValue(fields["xhttp-opts"])
	if xhttpOpts != nil {
		transportName = "xhttp"
		transport.Path = valueString(xhttpOpts["path"])
		transport.Host = valueString(xhttpOpts["host"])
	}
	if upgrade, ok := mapValue(fields["ws-opts"])["v2ray-http-upgrade"].(bool); ok && upgrade {
		transportName = "httpupgrade"
	}
	transport.Network = transportName
	tlsEnabled := boolValue(fields["tls"])
	if kind == domain.ProtocolTrojan {
		tlsEnabled = true
	}
	if protocol == "https" {
		tlsEnabled = true
	}
	tls := domain.TLSOptions{Enabled: tlsEnabled, SNI: valueString(fields["servername"]), ALPN: toStringSlice(fields["alpn"]), Insecure: boolValue(fields["skip-cert-verify"])}
	cipher := valueString(fields["cipher"])
	securityName := ""
	if kind == domain.ProtocolVMess {
		securityName = cipher
		cipher = ""
	}
	parsed := parsedNode{Name: name, Protocol: kind, Server: server, Port: port, Username: valueString(fields["username"]), Password: valueString(fields["password"]), UUID: valueString(fields["uuid"]), Cipher: cipher, Security: securityName, AlterID: intValue(fields["alterId"]), Flow: valueString(fields["flow"]), Transport: transport, TLS: tls, WGPublicKey: valueString(fields["public-key"]), WGLocalAddress: valueString(fields["ip"]), Extra: map[string]any{}}
	if plugin := valueString(fields["plugin"]); plugin != "" {
		parsed.Extra["plugin"] = plugin
		if options := mapValue(fields["plugin-opts"]); options != nil {
			parsed.Extra["plugin_opts"] = options
		}
	}
	if httpOpts := mapValue(fields["http-opts"]); httpOpts != nil {
		parsed.Extra["http_opts"] = httpOpts
	}
	if xhttpOpts != nil {
		parsed.Extra["xhttp_opts"] = xhttpOpts
	}
	if securityName := valueString(fields["security"]); securityName != "" {
		parsed.Extra["security"] = securityName
	}
	if reality := mapValue(fields["reality-opts"]); reality != nil {
		parsed.Extra["security"] = "reality"
		parsed.Extra["pbk"] = valueString(reality["public-key"])
		parsed.Extra["sid"] = valueString(reality["short-id"])
	}
	if fingerprint := valueString(fields["client-fingerprint"]); fingerprint != "" {
		parsed.Extra["fp"] = fingerprint
	}
	if kind == domain.ProtocolWireGuard {
		parsed.PrivateKey = valueString(fields["private-key"])
		for _, key := range []string{"preshared-key", "wg-mtu", "mtu", "allowed-ips", "reserved", "persistent-keepalive"} {
			if value, ok := fields[key]; ok {
				parsed.Extra[key] = value
			}
		}
		if ipv6 := valueString(fields["ipv6"]); ipv6 != "" {
			parsed.Extra["wg_ipv6_address"] = ipv6
		}
		if parsed.PrivateKey == "" || parsed.WGPublicKey == "" || (parsed.WGLocalAddress == "" && valueString(fields["ipv6"]) == "") {
			return parsedNode{}, fmt.Errorf("WireGuard requires private-key, public-key and at least one local IP address")
		}
	}
	if kind == domain.ProtocolVMess || kind == domain.ProtocolVLESS {
		if parsed.UUID == "" {
			return parsedNode{}, fmt.Errorf("UUID is required")
		}
	}
	if kind == domain.ProtocolTrojan || kind == domain.ProtocolShadowsocks {
		if parsed.Password == "" {
			return parsedNode{}, fmt.Errorf("password is required")
		}
	}
	if kind == domain.ProtocolWireGuard && parsed.PrivateKey == "" {
		return parsedNode{}, fmt.Errorf("WireGuard private-key is required")
	}
	if kind == domain.ProtocolShadowsocks && parsed.Cipher == "" {
		return parsedNode{}, fmt.Errorf("Shadowsocks cipher is required")
	}
	if len(parsed.Extra) == 0 {
		parsed.Extra = nil
	}
	return parsed, nil
}

func mapValue(value any) map[string]any {
	if result, ok := value.(map[string]any); ok {
		return result
	}
	return nil
}
func valueString(value any) string {
	if value == nil {
		return ""
	}
	return fmt.Sprint(value)
}
func boolValue(value any) bool {
	switch v := value.(type) {
	case bool:
		return v
	case string:
		return strings.EqualFold(v, "true")
	default:
		return false
	}
}
func toStringSlice(value any) []string {
	switch v := value.(type) {
	case []any:
		out := []string{}
		for _, item := range v {
			out = append(out, valueString(item))
		}
		return out
	case []string:
		return v
	case string:
		return splitCSV(v)
	}
	return nil
}
func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
