package migration

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
)

type MigrationReport struct {
	Subscriptions    int      `json:"subscriptions"`
	Nodes            int      `json:"nodes"`
	Chains           int      `json:"chains"`
	PortBindings     int      `json:"portBindings"`
	SecretsMoved     int      `json:"secretsMoved"`
	Warnings         []string `json:"warnings"`
	SecretReferences []string `json:"-"`
}

type legacyChainWrapper struct {
	ID, Name, SourceChainID string
	HopNodeIDs              []string
}

// ImportLegacyState converts the current Python state.json format. Secret values
// are moved into the OS credential vault before the returned workspace is saved.
// The caller must leave the source file untouched until the new database commits.
func ImportLegacyState(ctx context.Context, data []byte, secrets security.SecretStore) (workspace domain.Workspace, report MigrationReport, err error) {
	var legacy map[string]json.RawMessage
	if err = json.Unmarshal(data, &legacy); err != nil {
		return workspace, report, fmt.Errorf("decode legacy state.json: %w", err)
	}
	knownFields := []string{"subscriptions", "nodes", "chains", "port_mappings", "core_type", "active_base_node_id", "base_node_listen_port"}
	recognized := false
	for _, field := range knownFields {
		if _, ok := legacy[field]; ok {
			recognized = true
			break
		}
	}
	if !recognized {
		return workspace, report, errors.New("selected JSON file does not contain recognizable ChainPort legacy state fields")
	}
	workspace = domain.DefaultWorkspace()
	workspace.Settings.BaseListenHost = defaultString(stringField(legacy, "base_node_listen_host"), "127.0.0.1")
	allowLAN := boolField(legacy, "allow_lan", false)
	if net.ParseIP(workspace.Settings.BaseListenHost) == nil && !strings.EqualFold(workspace.Settings.BaseListenHost, "localhost") {
		report.Warnings = append(report.Warnings, "Ignored invalid legacy Base listener host and restored 127.0.0.1.")
		workspace.Settings.BaseListenHost = "127.0.0.1"
	}
	if !allowLAN && !isLoopbackAddress(workspace.Settings.BaseListenHost) {
		workspace.Settings.BaseListenHost = "127.0.0.1"
		report.Warnings = append(report.Warnings, "Reset the legacy Base listener to loopback because LAN access was disabled.")
	}
	basePort := defaultInt(intField(legacy, "base_node_listen_port"), 10808)
	if basePort < 1 || basePort > 65535 {
		return workspace, report, fmt.Errorf("legacy Base listener port %d is outside 1–65535", basePort)
	}
	workspace.Settings.BaseListenPort = uint16(basePort)
	createdRefs := []string{}
	defer func() {
		if err != nil && secrets != nil {
			for _, reference := range createdRefs {
				_ = secrets.Delete(ctx, reference)
			}
		}
	}()
	putSecret := func(value string) (string, error) {
		if value == "" {
			return "", nil
		}
		if secrets == nil || !secrets.Available() {
			return "", security.ErrUnavailable
		}
		reference, idErr := newSecretReference()
		if idErr != nil {
			return "", idErr
		}
		if putErr := secrets.Put(ctx, reference, value); putErr != nil {
			return "", putErr
		}
		createdRefs = append(createdRefs, reference)
		report.SecretReferences = append(report.SecretReferences, reference)
		report.SecretsMoved++
		return reference, nil
	}

	var subscriptions []map[string]json.RawMessage
	if err = decodeField(legacy, "subscriptions", &subscriptions); err != nil {
		return workspace, report, err
	}
	subscriptionIDs := map[string]string{}
	for _, item := range subscriptions {
		id, name := stringField(item, "sub_id"), stringField(item, "name")
		if id == "" {
			id, err = newSecretReference()
			if err != nil {
				return workspace, report, err
			}
		}
		urlRef, putErr := putSecret(stringField(item, "url"))
		if putErr != nil {
			return workspace, report, fmt.Errorf("move subscription URL for %q to credential vault: %w", name, putErr)
		}
		headerRefs := map[string]string{}
		var headers map[string]json.RawMessage
		if raw := item["http_headers"]; len(raw) > 0 {
			if decodeErr := json.Unmarshal(raw, &headers); decodeErr != nil {
				return workspace, report, fmt.Errorf("decode HTTP headers for subscription %q: %w", name, decodeErr)
			}
		}
		for header, raw := range headers {
			var value string
			if decodeErr := json.Unmarshal(raw, &value); decodeErr != nil {
				return workspace, report, fmt.Errorf("HTTP header %q for subscription %q must be a string", header, name)
			}
			ref, putErr := putSecret(value)
			if putErr != nil {
				return workspace, report, fmt.Errorf("move HTTP header %q for subscription %q to credential vault: %w", header, name, putErr)
			}
			if ref != "" {
				headerRefs[header] = ref
			}
		}
		legacyMetadata := map[string]string{}
		for _, key := range []string{"convert_target_type", "previous_proxy_remarks", "next_proxy_remarks", "custom_config_core", "custom_config_socks_port", "remarks_memo"} {
			if value := scalarStringField(item, key); value != "" {
				legacyMetadata[key] = value
			}
		}
		legacyMetadataRef := ""
		if len(legacyMetadata) > 0 {
			encoded, marshalErr := json.Marshal(legacyMetadata)
			if marshalErr != nil {
				return workspace, report, marshalErr
			}
			compressed, compressErr := security.EncodeMetadataJSON(encoded)
			if compressErr != nil {
				return workspace, report, compressErr
			}
			legacyMetadataRef, putErr = putSecret(compressed)
			if putErr != nil {
				return workspace, report, fmt.Errorf("move legacy subscription metadata for %q: %w", name, putErr)
			}
		}
		format := stringField(item, "sub_type")
		if format == "" {
			format = "auto"
		}
		updateMinutes := intField(item, "update_interval")
		if _, exists := item["update_interval"]; !exists {
			updateMinutes = intField(item, "auto_update_interval")
		}
		workspace.Subscriptions = append(workspace.Subscriptions, domain.Subscription{
			ID: id, Name: name, URLSecretRef: urlRef, Format: format,
			Enabled: boolField(item, "enable_update", true), UpdateMinutes: updateMinutes,
			UserAgent: stringField(item, "user_agent"), HeaderSecretRefs: headerRefs,
			LastUpdated: stringField(item, "last_update"), LastAttempt: stringField(item, "last_update"), NodeCount: intField(item, "node_count"),
			Sort: intField(item, "sort"), RemarksFilter: stringField(item, "remarks_filter"), LegacyMetadataRef: legacyMetadataRef,
		})
		if name != "" {
			subscriptionIDs[name] = id
		}
	}
	report.Subscriptions = len(workspace.Subscriptions)

	var nodes []map[string]json.RawMessage
	if err = decodeField(legacy, "nodes", &nodes); err != nil {
		return workspace, report, err
	}
	wrapperNodes := map[string]legacyChainWrapper{}
	wrapperOrder := []legacyChainWrapper{}
	for _, item := range nodes {
		protocol := stringField(item, "node_type")
		if protocol == "chain" {
			extra := map[string]json.RawMessage{}
			if len(item["extra"]) > 0 {
				_ = json.Unmarshal(item["extra"], &extra)
			}
			wrapper := legacyChainWrapper{ID: stringField(item, "node_id"), Name: stringField(item, "name"), SourceChainID: stringField(extra, "source_chain_id"), HopNodeIDs: rawStringSlice(extra["chain_hop_node_ids"])}
			if wrapper.ID != "" {
				wrapperNodes[wrapper.ID] = wrapper
				wrapperOrder = append(wrapperOrder, wrapper)
			}
			continue
		}
		if protocol == "ss" {
			protocol = string(domain.ProtocolShadowsocks)
		}
		if protocol == "wg" {
			protocol = string(domain.ProtocolWireGuard)
		}
		if protocol == "" {
			protocol = string(domain.ProtocolUnknown)
		}
		nodePort := intField(item, "port")
		if nodePort < 1 || nodePort > 65535 {
			return workspace, report, fmt.Errorf("legacy node %q has invalid port %d", stringField(item, "node_id"), nodePort)
		}
		node := domain.Node{
			ID: stringField(item, "node_id"), Name: stringField(item, "name"), Protocol: domain.Protocol(protocol),
			Server: stringField(item, "server"), Port: uint16(nodePort),
			Transport: domain.Transport{Network: stringField(item, "network"), Path: stringField(item, "path"), Host: stringField(item, "host")},
			TLS:       domain.TLSOptions{Enabled: boolField(item, "tls_enabled", false), SNI: stringField(item, "sni"), ALPN: stringSliceField(item, "alpn")},
			Options:   map[string]string{}, WGPublicKey: stringField(item, "wg_public_key"), WGLocalAddress: stringField(item, "wg_local_address"),
			Cipher: scalarStringField(item, "encryption"), Security: scalarStringField(item, "security"), Flow: scalarStringField(item, "flow"), AlterID: intField(item, "alter_id"),
		}
		if node.Transport.Network == "" {
			node.Transport.Network = "tcp"
		}
		if node.ID == "" || node.Name == "" || node.Server == "" || node.Port == 0 {
			return workspace, report, fmt.Errorf("legacy node %q is missing a required ID, name, server or port", node.ID)
		}
		var secretErr error
		if node.Credentials.UsernameRef, secretErr = putSecret(stringField(item, "username")); secretErr != nil {
			return workspace, report, fmt.Errorf("move username for node %q: %w", node.ID, secretErr)
		}
		if node.Credentials.PasswordRef, secretErr = putSecret(stringField(item, "password")); secretErr != nil {
			return workspace, report, fmt.Errorf("move password for node %q: %w", node.ID, secretErr)
		}
		if node.Credentials.UUIDRef, secretErr = putSecret(stringField(item, "uuid_str")); secretErr != nil {
			return workspace, report, fmt.Errorf("move UUID for node %q: %w", node.ID, secretErr)
		}
		if node.Credentials.PrivateKeyRef, secretErr = putSecret(stringField(item, "wg_private_key")); secretErr != nil {
			return workspace, report, fmt.Errorf("move WireGuard private key for node %q: %w", node.ID, secretErr)
		}
		if sourceName := stringField(item, "source_sub"); sourceName != "" {
			node.SourceID = subscriptionIDs[sourceName]
		}
		metadata := map[string]json.RawMessage{}
		if raw := item["extra"]; len(raw) > 0 && string(raw) != "null" && string(raw) != "{}" {
			metadata["extra"] = raw
		}
		if len(metadata) > 0 {
			encoded, marshalErr := json.Marshal(metadata)
			if marshalErr != nil {
				return workspace, report, marshalErr
			}
			compressed, compressionErr := security.EncodeMetadataJSON(encoded)
			if compressionErr != nil {
				return workspace, report, compressionErr
			}
			if node.SourceMetadataRef, secretErr = putSecret(compressed); secretErr != nil {
				return workspace, report, fmt.Errorf("preserve source metadata for node %q in credential vault: %w", node.ID, secretErr)
			}
		}
		if raw := item["raw_dict"]; len(raw) > 0 && string(raw) != "null" && string(raw) != "{}" {
			report.Warnings = append(report.Warnings, fmt.Sprintf("Omitted debug-only raw_dict for node %q; runtime protocol metadata in extra was preserved in the credential vault.", node.Name))
		}
		workspace.Nodes = append(workspace.Nodes, node)
	}
	report.Nodes = len(workspace.Nodes)

	var legacyChains []map[string]json.RawMessage
	if err = decodeField(legacy, "chains", &legacyChains); err != nil {
		return workspace, report, err
	}
	for _, item := range legacyChains {
		workspace.Chains = append(workspace.Chains, domain.Chain{ID: stringField(item, "chain_id"), Name: stringField(item, "name"), HopNodeIDs: stringSliceField(item, "hop_node_ids")})
	}
	chainIDs := map[string]bool{}
	for _, chain := range workspace.Chains {
		chainIDs[chain.ID] = true
	}
	for _, wrapper := range wrapperOrder {
		id := wrapper.SourceChainID
		if id == "" {
			id = wrapper.ID
		}
		if id == "" || len(wrapper.HopNodeIDs) == 0 || chainIDs[id] {
			continue
		}
		workspace.Chains = append(workspace.Chains, domain.Chain{ID: id, Name: defaultString(wrapper.Name, "Legacy Chain"), HopNodeIDs: append([]string(nil), wrapper.HopNodeIDs...)})
		chainIDs[id] = true
	}
	validNodes := map[string]bool{}
	for _, node := range workspace.Nodes {
		validNodes[node.ID] = true
	}
	var expandHop func(string, map[string]bool) ([]string, bool)
	expandHop = func(id string, stack map[string]bool) ([]string, bool) {
		if validNodes[id] {
			return []string{id}, true
		}
		wrapper, ok := wrapperNodes[id]
		if !ok || stack[id] || len(wrapper.HopNodeIDs) == 0 {
			return nil, false
		}
		stack[id] = true
		defer delete(stack, id)
		expanded := []string{}
		for _, nested := range wrapper.HopNodeIDs {
			parts, ok := expandHop(nested, stack)
			if !ok {
				return nil, false
			}
			expanded = append(expanded, parts...)
		}
		return expanded, len(expanded) > 0
	}
	validChains := make([]domain.Chain, 0, len(workspace.Chains))
	for _, chain := range workspace.Chains {
		expanded := []string{}
		valid := true
		for _, hop := range chain.HopNodeIDs {
			parts, ok := expandHop(hop, map[string]bool{})
			if !ok {
				valid = false
				break
			}
			expanded = append(expanded, parts...)
		}
		if !valid || len(expanded) == 0 {
			return workspace, report, fmt.Errorf("legacy Chain %q contains an unresolved or cyclic hop reference", chain.Name)
		}
		chain.HopNodeIDs = expanded
		validChains = append(validChains, chain)
	}
	workspace.Chains = validChains
	report.Chains = len(workspace.Chains)
	var mappings []map[string]json.RawMessage
	if err = decodeField(legacy, "port_mappings", &mappings); err != nil {
		return workspace, report, err
	}
	for _, item := range mappings {
		bindingID := stringField(item, "mapping_id")
		if bindingID == "" {
			bindingID, err = newSecretReference()
			if err != nil {
				return workspace, report, err
			}
		}
		mappingPort := intField(item, "listen_port")
		if mappingPort < 1 || mappingPort > 65535 {
			return workspace, report, fmt.Errorf("legacy port mapping %q has invalid port %d", bindingID, mappingPort)
		}
		workspace.PortBindings = append(workspace.PortBindings, domain.PortBinding{ID: bindingID, ChainID: stringField(item, "chain_id"), ListenHost: defaultString(stringField(item, "listen_host"), "127.0.0.1"), ListenPort: uint16(mappingPort), Remark: stringField(item, "remark")})
	}
	validChainIDs := map[string]bool{}
	for _, chain := range workspace.Chains {
		validChainIDs[chain.ID] = true
	}
	filteredMappings := []domain.PortBinding{}
	seenMappingIDs := map[string]bool{}
	seenChainMappings := map[string]bool{}
	seenPorts := map[uint16]bool{workspace.Settings.BaseListenPort: true}
	for _, binding := range workspace.PortBindings {
		if !validChainIDs[binding.ChainID] {
			report.Warnings = append(report.Warnings, fmt.Sprintf("Skipped orphaned port mapping %q for missing Chain %q.", binding.ID, binding.ChainID))
			continue
		}
		if seenChainMappings[binding.ChainID] || seenPorts[binding.ListenPort] {
			report.Warnings = append(report.Warnings, fmt.Sprintf("Skipped duplicate or colliding port mapping %q.", binding.ID))
			continue
		}
		if (net.ParseIP(binding.ListenHost) == nil && !strings.EqualFold(binding.ListenHost, "localhost")) || (!allowLAN && !isLoopbackAddress(binding.ListenHost)) {
			binding.ListenHost = "127.0.0.1"
			report.Warnings = append(report.Warnings, fmt.Sprintf("Reset invalid listen host on port mapping %q to 127.0.0.1.", binding.ID))
		}
		if seenMappingIDs[binding.ID] {
			binding.ID = "legacy-" + binding.ID
		}
		seenMappingIDs[binding.ID] = true
		seenChainMappings[binding.ChainID] = true
		seenPorts[binding.ListenPort] = true
		filteredMappings = append(filteredMappings, binding)
	}
	workspace.PortBindings = filteredMappings
	usedPorts := map[uint16]bool{workspace.Settings.BaseListenPort: true}
	for _, binding := range workspace.PortBindings {
		usedPorts[binding.ListenPort] = true
	}
	for _, chain := range workspace.Chains {
		found := false
		for _, binding := range workspace.PortBindings {
			if binding.ChainID == chain.ID {
				found = true
				break
			}
		}
		if found {
			continue
		}
		var port uint16
		for candidate := uint32(20001); candidate <= 65535; candidate++ {
			if !usedPorts[uint16(candidate)] {
				port = uint16(candidate)
				break
			}
		}
		if port == 0 {
			return workspace, report, errors.New("no available local ports remain while migrating legacy Chains")
		}
		workspace.PortBindings = append(workspace.PortBindings, domain.PortBinding{ID: "legacy-" + chain.ID, ChainID: chain.ID, ListenHost: "127.0.0.1", ListenPort: port})
		usedPorts[port] = true
		report.Warnings = append(report.Warnings, fmt.Sprintf("Allocated local port %d for legacy Chain %q because its old profile had no port mapping.", port, chain.Name))
	}
	report.PortBindings = len(workspace.PortBindings)

	workspace.ActiveNodeID = stringField(legacy, "active_base_node_id")
	activeExists := false
	for _, node := range workspace.Nodes {
		if node.ID == workspace.ActiveNodeID {
			activeExists = true
			break
		}
	}
	if !activeExists && len(workspace.Nodes) > 0 {
		workspace.ActiveNodeID = workspace.Nodes[0].ID
		report.Warnings = append(report.Warnings, "Legacy active Base Node was missing or invalid; selected the first imported Base Node.")
	}
	workspace.TUN.Enabled = boolField(legacy, "enable_tun", false)
	if chainID := stringField(legacy, "tun_chain_id"); chainID != "" {
		if wrapper, ok := wrapperNodes[chainID]; ok && wrapper.SourceChainID != "" {
			chainID = wrapper.SourceChainID
		}
		workspace.TUN.Kind, workspace.TUN.TargetID = domain.TUNBindingChain, chainID
	} else if nodeID := stringField(legacy, "tun_node_id"); nodeID != "" {
		if wrapper, ok := wrapperNodes[nodeID]; ok {
			target := wrapper.SourceChainID
			if target == "" {
				target = wrapper.ID
			}
			workspace.TUN.Kind, workspace.TUN.TargetID = domain.TUNBindingChain, target
		} else {
			workspace.TUN.Kind, workspace.TUN.TargetID = domain.TUNBindingNode, nodeID
		}
	} else if workspace.TUN.Enabled && workspace.ActiveNodeID != "" {
		workspace.TUN.Kind, workspace.TUN.TargetID = domain.TUNBindingNode, workspace.ActiveNodeID
	} else {
		workspace.TUN.Kind = domain.TUNBindingNone
		workspace.TUN.Enabled = false
	}
	if workspace.TUN.Kind == domain.TUNBindingChain {
		found := false
		for _, chain := range workspace.Chains {
			if chain.ID == workspace.TUN.TargetID {
				found = true
				break
			}
		}
		if !found {
			report.Warnings = append(report.Warnings, "Legacy TUN Chain target was missing; TUN binding was cleared.")
			workspace.TUN = domain.TUNBinding{Kind: domain.TUNBindingNone}
		}
	}
	if workspace.TUN.Kind == domain.TUNBindingNode {
		found := false
		for _, node := range workspace.Nodes {
			if node.ID == workspace.TUN.TargetID {
				found = true
				break
			}
		}
		if !found {
			report.Warnings = append(report.Warnings, "Legacy TUN Base Node target was missing; TUN binding was cleared.")
			workspace.TUN = domain.TUNBinding{Kind: domain.TUNBindingNone}
		}
	}

	workspace.Settings.Core.Type = defaultString(stringField(legacy, "core_type"), "sing-box")
	if workspace.Settings.Core.Type != "sing-box" && workspace.Settings.Core.Type != "xray" && workspace.Settings.Core.Type != "mihomo" {
		report.Warnings = append(report.Warnings, "Unsupported legacy core type; selected sing-box until a supported executable is configured.")
		workspace.Settings.Core.Type = "sing-box"
	}
	workspace.Settings.Core.LogLevel = defaultString(stringField(legacy, "log_level"), "warning")
	legacyPaths := map[string]string{}
	if raw := legacy["core_exe_paths"]; len(raw) > 0 {
		if decodeErr := json.Unmarshal(raw, &legacyPaths); decodeErr != nil {
			return workspace, report, fmt.Errorf("decode legacy core executable paths: %w", decodeErr)
		}
	}
	if oldPath := stringField(legacy, "core_exe_path"); oldPath != "" && legacyPaths[workspace.Settings.Core.Type] == "" {
		legacyPaths[workspace.Settings.Core.Type] = oldPath
	}
	for _, coreName := range []string{"sing-box", "xray", "mihomo"} {
		if path := strings.TrimSpace(legacyPaths[coreName]); path != "" {
			if validLegacyExecutable(path) {
				workspace.Settings.Core.Executable[coreName] = path
			} else {
				report.Warnings = append(report.Warnings, fmt.Sprintf("Ignored unavailable or cross-platform %s executable path; configure it in Settings.", coreName))
			}
		}
	}
	workspace.Settings.Network = domain.NetworkSettings{
		EnableIPv6: boolField(legacy, "enable_ipv6", false), EnableUDP: boolField(legacy, "enable_udp", true),
		EnableSniffing: boolField(legacy, "enable_sniffing", true), AllowLAN: allowLAN,
		EnableMux: boolField(legacy, "enable_mux", false), AllowInsecure: boolField(legacy, "allow_insecure", false),
		EnableFragment: boolField(legacy, "enable_fragment", false), EnableFinalFragment: boolField(legacy, "enable_final_fragment", boolField(legacy, "enable_fragment", false)),
		XrayFragmentPackets: stringField(legacy, "xray_fragment_packets"), XrayFragmentLengths: stringSliceField(legacy, "xray_fragment_lengths"),
		XrayFragmentDelays: stringSliceField(legacy, "xray_fragment_delays"), XrayFragmentMaxSplit: intField(legacy, "xray_fragment_max_split"),
		SingboxMuxProtocol: defaultString(stringField(legacy, "singbox_mux_protocol"), "h2mux"), BlockQUIC: boolField(legacy, "block_quic", true),
		RemoteDNSURL: defaultString(stringField(legacy, "remote_dns_url"), "https://cloudflare-dns.com/dns-query"),
		BootstrapDNS: defaultString(stringField(legacy, "bootstrap_dns"), "119.29.29.29"),
	}
	workspace.Settings.AutoStart = boolField(legacy, "auto_start_core", false)
	workspace.Settings.RunOnStartup = boolField(legacy, "run_on_startup", false)
	workspace.Settings.MinimizeOnStart = boolField(legacy, "minimize_on_start", false)
	workspace.Settings.CloseToTray = boolField(legacy, "close_to_tray", true)
	if err = workspace.Validate(); err != nil {
		return workspace, report, fmt.Errorf("legacy workspace violates new domain invariants: %w", err)
	}
	if report.SecretsMoved > 0 {
		report.Warnings = append(report.Warnings, "Credentials, subscription URLs, HTTP header values and protocol-specific node metadata were moved to the OS credential vault; the original state.json has not been modified.")
	}
	return workspace, report, nil
}

func validLegacyExecutable(path string) bool {
	if !filepath.IsAbs(path) {
		return false
	}
	info, err := os.Stat(path)
	if err != nil || info.IsDir() {
		return false
	}
	if runtime.GOOS != "windows" && info.Mode().Perm()&0o111 == 0 {
		return false
	}
	return true
}

func decodeField(source map[string]json.RawMessage, key string, target any) error {
	if raw := source[key]; len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	if err := json.Unmarshal(source[key], target); err != nil {
		return fmt.Errorf("decode legacy field %q: %w", key, err)
	}
	return nil
}

func stringField(source map[string]json.RawMessage, key string) string {
	var value string
	_ = json.Unmarshal(source[key], &value)
	return value
}

func scalarStringField(source map[string]json.RawMessage, key string) string {
	raw := source[key]
	if len(raw) == 0 || string(raw) == "null" {
		return ""
	}
	var value string
	if json.Unmarshal(raw, &value) == nil {
		return value
	}
	return string(raw)
}
func intField(source map[string]json.RawMessage, key string) int {
	var value int
	if json.Unmarshal(source[key], &value) == nil {
		return value
	}
	var number json.Number
	if json.Unmarshal(source[key], &number) == nil {
		n, _ := strconv.Atoi(number.String())
		return n
	}
	return 0
}
func boolField(source map[string]json.RawMessage, key string, fallback bool) bool {
	if len(source[key]) == 0 {
		return fallback
	}
	var value bool
	if json.Unmarshal(source[key], &value) != nil {
		return fallback
	}
	return value
}
func stringSliceField(source map[string]json.RawMessage, key string) []string {
	var values []string
	_ = json.Unmarshal(source[key], &values)
	return values
}
func rawStringSlice(raw json.RawMessage) []string {
	var values []string
	_ = json.Unmarshal(raw, &values)
	return values
}
func isLoopbackAddress(value string) bool {
	ip := net.ParseIP(value)
	return ip != nil && ip.IsLoopback() || strings.EqualFold(value, "localhost")
}

func defaultString(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}
func defaultInt(value, fallback int) int {
	if value == 0 {
		return fallback
	}
	return value
}
func newSecretReference() (string, error) {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", err
	}
	return "legacy-" + hex.EncodeToString(value[:]), nil
}
