package parser

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"strings"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
)

type NodeSecretWriter interface {
	Put(context.Context, string, string) error
	Available() bool
}

type parsedNode struct {
	Name, Server, Username, Password, UUID, PrivateKey string
	Protocol                                           domain.Protocol
	Port                                               uint16
	Cipher, Security, Flow                             string
	AlterID                                            int
	Transport                                          domain.Transport
	TLS                                                domain.TLSOptions
	WGPublicKey, WGLocalAddress                        string
	Extra                                              map[string]any
}

func ParseShareLinks(ctx context.Context, text, sourceID string, secrets NodeSecretWriter) ([]domain.Node, []error) {
	lines := strings.FieldsFunc(text, func(r rune) bool { return r == '\n' || r == '\r' })
	var nodes []domain.Node
	var errs []error
	for i, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parsed, err := parseShareLink(line)
		if err != nil {
			errs = append(errs, fmt.Errorf("line %d: %w", i+1, err))
			continue
		}
		node, err := persistParsedNode(ctx, parsed, sourceID, secrets)
		if err != nil {
			errs = append(errs, fmt.Errorf("line %d (%s): %w", i+1, parsed.Name, err))
			continue
		}
		nodes = append(nodes, node)
	}
	return nodes, errs
}

func parseShareLink(raw string) (parsedNode, error) {
	if strings.HasPrefix(raw, "vmess://") {
		return parseVMess(raw)
	}
	if strings.HasPrefix(raw, "ss://") {
		return parseShadowsocks(raw)
	}
	if strings.HasPrefix(raw, "vless://") || strings.HasPrefix(raw, "trojan://") || strings.HasPrefix(raw, "socks5://") || strings.HasPrefix(raw, "socks://") || strings.HasPrefix(raw, "http://") || strings.HasPrefix(raw, "https://") {
		return parseURLShare(raw)
	}
	return parsedNode{}, fmt.Errorf("unsupported share-link scheme")
}

func parseVMess(raw string) (parsedNode, error) {
	encoded := strings.TrimSpace(strings.TrimPrefix(raw, "vmess://"))
	data, err := decodeBase64(encoded)
	if err != nil {
		return parsedNode{}, fmt.Errorf("decode VMess payload: %w", err)
	}
	var value map[string]any
	if err := json.Unmarshal(data, &value); err != nil {
		return parsedNode{}, fmt.Errorf("decode VMess JSON: %w", err)
	}
	port, err := parsePort(value["port"])
	if err != nil {
		return parsedNode{}, err
	}
	server, uuid := stringValue(value["add"]), stringValue(value["id"])
	if server == "" || uuid == "" {
		return parsedNode{}, fmt.Errorf("VMess requires add and id")
	}
	alpn := stringList(value["alpn"])
	tlsValue := strings.ToLower(stringValue(value["tls"]))
	reality := tlsValue == "reality"
	tls := tlsValue == "tls" || tlsValue == "true" || tlsValue == "1" || reality
	extra := map[string]any{"vmess": value}
	if fp := stringValue(value["fp"]); fp != "" {
		extra["fp"] = fp
	}
	if reality {
		extra["security"] = "reality"
		for _, key := range []string{"pbk", "sid", "spx"} {
			if v := stringValue(value[key]); v != "" {
				extra[key] = v
			}
		}
	}
	network := defaultValue(stringValue(value["net"]), "tcp")
	if network == "gun" {
		network = "grpc"
	}
	return parsedNode{Name: defaultValue(stringValue(value["ps"]), "VMess"), Protocol: domain.ProtocolVMess, Server: server, Port: port, UUID: uuid, AlterID: intValue(value["aid"]), Security: defaultValue(stringValue(value["scy"]), "auto"), Transport: domain.Transport{Network: network, Host: stringValue(value["host"]), Path: stringValue(value["path"])}, TLS: domain.TLSOptions{Enabled: tls, SNI: stringValue(value["sni"]), ALPN: alpn}, Extra: extra}, nil
}

func parseURLShare(raw string) (parsedNode, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return parsedNode{}, err
	}
	protocol := domain.Protocol(strings.ToLower(u.Scheme))
	if u.Scheme == "https" {
		protocol = domain.ProtocolHTTP
	}
	switch protocol {
	case domain.ProtocolVLESS, domain.ProtocolTrojan, domain.ProtocolSOCKS5, domain.ProtocolHTTP:
	case "socks":
		protocol = domain.ProtocolSOCKS5
	default:
		return parsedNode{}, fmt.Errorf("unsupported scheme %q", u.Scheme)
	}
	host := u.Hostname()
	portNumber, err := strconv.Atoi(u.Port())
	if err != nil || portNumber < 1 || portNumber > 65535 {
		return parsedNode{}, fmt.Errorf("invalid server port")
	}
	var username, password string
	if u.User != nil {
		username = u.User.Username()
		password, _ = u.User.Password()
	}
	query := u.Query()
	name := u.Fragment
	if name == "" {
		name = strings.ToUpper(string(protocol))
	}
	network := defaultValue(query.Get("type"), "tcp")
	if network == "gun" {
		network = "grpc"
	}
	node := parsedNode{Name: name, Protocol: protocol, Server: host, Port: uint16(portNumber), Username: username, Password: password, Transport: domain.Transport{Network: network, Host: query.Get("host"), Path: query.Get("path")}, Extra: map[string]any{"query": map[string][]string(query)}}
	switch protocol {
	case domain.ProtocolVLESS:
		node.UUID = username
		node.Username = ""
		securityName := query.Get("security")
		node.Flow = query.Get("flow")
		node.TLS = domain.TLSOptions{Enabled: securityName == "tls" || securityName == "reality", SNI: query.Get("sni"), ALPN: splitCSV(query.Get("alpn")), Insecure: query.Get("allowInsecure") == "1"}
	case domain.ProtocolTrojan:
		node.Password = username
		node.Username = ""
		if password != "" {
			node.Password = username + ":" + password
		}
		node.TLS = domain.TLSOptions{Enabled: true, SNI: query.Get("sni"), ALPN: splitCSV(query.Get("alpn")), Insecure: query.Get("allowInsecure") == "1"}
	case domain.ProtocolSOCKS5, domain.ProtocolHTTP:
		if protocol == domain.ProtocolSOCKS5 && username != "" && password == "" && !strings.Contains(username, ":") {
			if decoded, decodeErr := decodeBase64(username); decodeErr == nil && strings.Contains(string(decoded), ":") {
				parts := strings.SplitN(string(decoded), ":", 2)
				node.Username, node.Password = parts[0], parts[1]
			}
		}
		node.TLS = domain.TLSOptions{Enabled: u.Scheme == "https"}
	}
	if protocol == domain.ProtocolVLESS && node.UUID == "" {
		return parsedNode{}, fmt.Errorf("VLESS URI requires UUID userinfo")
	}
	if protocol == domain.ProtocolTrojan && node.Password == "" {
		return parsedNode{}, fmt.Errorf("Trojan URI requires password userinfo")
	}
	return node, nil
}

func parseShadowsocks(raw string) (parsedNode, error) {
	u, err := url.Parse(raw)
	if err != nil {
		return parsedNode{}, err
	}
	var method, password, host string
	if u.User != nil {
		userinfo, decodeErr := u.User.Username(), error(nil)
		if strings.Contains(userinfo, ":") {
			method, password = strings.SplitN(userinfo, ":", 2)[0], strings.SplitN(userinfo, ":", 2)[1]
		} else {
			var decoded []byte
			decoded, decodeErr = decodeBase64(userinfo)
			if decodeErr == nil {
				pair := strings.SplitN(string(decoded), ":", 2)
				if len(pair) == 2 {
					method, password = pair[0], pair[1]
				}
			}
		}
		if decodeErr != nil {
			return parsedNode{}, decodeErr
		}
		host = u.Host
	} else {
		payload := strings.TrimPrefix(raw, "ss://")
		if i := strings.IndexByte(payload, '#'); i >= 0 {
			payload = payload[:i]
		}
		if i := strings.IndexByte(payload, '?'); i >= 0 {
			payload = payload[:i]
		}
		decoded, decodeErr := decodeBase64(strings.Trim(payload, "/"))
		if decodeErr != nil {
			return parsedNode{}, decodeErr
		}
		at := strings.LastIndex(string(decoded), "@")
		if at < 0 {
			return parsedNode{}, fmt.Errorf("legacy Shadowsocks payload missing @")
		}
		pair := strings.SplitN(string(decoded[:at]), ":", 2)
		if len(pair) != 2 {
			return parsedNode{}, fmt.Errorf("Shadowsocks credentials must be method:password")
		}
		method, password, host = pair[0], pair[1], string(decoded[at+1:])
	}
	server, port, err := splitHostPort(host)
	if err != nil {
		return parsedNode{}, err
	}
	name := u.Fragment
	if name == "" {
		name = "Shadowsocks"
	}
	extra := map[string]any{}
	if plugin := u.Query().Get("plugin"); plugin != "" {
		pluginName, pluginOptions := parseShadowsocksPlugin(plugin)
		extra["plugin"] = pluginName
		if len(pluginOptions) > 0 {
			extra["plugin_opts"] = pluginOptions
		}
	}
	return parsedNode{Name: name, Protocol: domain.ProtocolShadowsocks, Server: server, Port: port, Password: password, Cipher: method, Transport: domain.Transport{Network: "tcp"}, Extra: extra}, nil
}

func parseShadowsocksPlugin(value string) (string, map[string]any) {
	parts := strings.Split(value, ";")
	name := strings.TrimSpace(parts[0])
	options := map[string]any{}
	for _, part := range parts[1:] {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if strings.Contains(part, "=") {
			pair := strings.SplitN(part, "=", 2)
			options[pair[0]] = pair[1]
		} else {
			options[part] = true
		}
	}
	if name == "obfs-local" {
		name = "obfs"
		if mode, ok := options["obfs"]; ok {
			options["mode"] = mode
			delete(options, "obfs")
		}
		if host, ok := options["obfs-host"]; ok {
			options["host"] = host
			delete(options, "obfs-host")
		}
	}
	return name, options
}

func persistParsedNode(ctx context.Context, p parsedNode, sourceID string, secrets NodeSecretWriter) (domain.Node, error) {
	if secrets == nil || !secrets.Available() {
		if p.Username != "" || p.Password != "" || p.UUID != "" || p.PrivateKey != "" || len(p.Extra) > 0 {
			return domain.Node{}, security.ErrUnavailable
		}
	}
	refs := domain.Credentials{}
	created := []string{}
	put := func(value string) (string, error) {
		if value == "" {
			return "", nil
		}
		ref, err := newReference()
		if err != nil {
			return "", err
		}
		if err := secrets.Put(ctx, ref, value); err != nil {
			return "", err
		}
		created = append(created, ref)
		return ref, nil
	}
	var err error
	if refs.UsernameRef, err = put(p.Username); err != nil {
		return domain.Node{}, err
	}
	if refs.PasswordRef, err = put(p.Password); err != nil {
		rollback(ctx, secrets, created)
		return domain.Node{}, err
	}
	if refs.UUIDRef, err = put(p.UUID); err != nil {
		rollback(ctx, secrets, created)
		return domain.Node{}, err
	}
	if refs.PrivateKeyRef, err = put(p.PrivateKey); err != nil {
		rollback(ctx, secrets, created)
		return domain.Node{}, err
	}
	var metadataRef string
	if len(p.Extra) > 0 {
		data, marshalErr := json.Marshal(map[string]any{"extra": p.Extra})
		if marshalErr != nil {
			rollback(ctx, secrets, created)
			return domain.Node{}, marshalErr
		}
		encoded, encErr := security.EncodeMetadataJSON(data)
		if encErr != nil {
			rollback(ctx, secrets, created)
			return domain.Node{}, encErr
		}
		metadataRef, err = put(encoded)
		if err != nil {
			rollback(ctx, secrets, created)
			return domain.Node{}, err
		}
	}
	id, err := newReference()
	if err != nil {
		rollback(ctx, secrets, created)
		return domain.Node{}, err
	}
	return domain.Node{ID: id, Name: p.Name, Protocol: p.Protocol, Server: p.Server, Port: p.Port, Credentials: refs, Transport: p.Transport, TLS: p.TLS, SourceID: sourceID, SourceMetadataRef: metadataRef, Cipher: p.Cipher, Security: p.Security, Flow: p.Flow, AlterID: p.AlterID, ALPN: p.TLS.ALPN, WGPublicKey: p.WGPublicKey, WGLocalAddress: p.WGLocalAddress}, nil
}

func decodeBase64(value string) ([]byte, error) {
	value = strings.TrimSpace(value)
	for _, enc := range []*base64.Encoding{base64.RawStdEncoding, base64.StdEncoding, base64.RawURLEncoding, base64.URLEncoding} {
		decoded, err := enc.DecodeString(value)
		if err == nil {
			return decoded, nil
		}
	}
	return nil, fmt.Errorf("invalid base64 payload")
}
func parsePort(value any) (uint16, error) {
	n, err := strconv.Atoi(fmt.Sprint(value))
	if err != nil || n < 1 || n > 65535 {
		return 0, fmt.Errorf("invalid port %q", fmt.Sprint(value))
	}
	return uint16(n), nil
}
func splitHostPort(value string) (string, uint16, error) {
	host, portText, err := net.SplitHostPort(value)
	if err != nil {
		return "", 0, fmt.Errorf("invalid host:port %q: %w", value, err)
	}
	port, err := parsePort(portText)
	return host, port, err
}
func stringValue(value any) string {
	if value == nil {
		return ""
	}
	return fmt.Sprint(value)
}
func intValue(value any) int { n, _ := strconv.Atoi(stringValue(value)); return n }
func stringList(value any) []string {
	switch v := value.(type) {
	case []any:
		out := []string{}
		for _, item := range v {
			out = append(out, stringValue(item))
		}
		return out
	case string:
		return splitCSV(v)
	}
	return nil
}
func splitCSV(value string) []string {
	if value == "" {
		return nil
	}
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		if p := strings.TrimSpace(part); p != "" {
			out = append(out, p)
		}
	}
	return out
}
func defaultValue(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}
func rollback(ctx context.Context, secrets NodeSecretWriter, refs []string) {
	for _, ref := range refs {
		if deleter, ok := secrets.(interface {
			Delete(context.Context, string) error
		}); ok {
			_ = deleter.Delete(ctx, ref)
		}
	}
}
func newReference() (string, error) {
	var bytes [16]byte
	if _, err := rand.Read(bytes[:]); err != nil {
		return "", err
	}
	return fmt.Sprintf("node-%x", bytes), nil
}
