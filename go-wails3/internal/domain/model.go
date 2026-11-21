package domain

import (
	"errors"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"strings"
)

type Protocol string

const (
	ProtocolVMess       Protocol = "vmess"
	ProtocolVLESS       Protocol = "vless"
	ProtocolTrojan      Protocol = "trojan"
	ProtocolShadowsocks Protocol = "shadowsocks"
	ProtocolWireGuard   Protocol = "wireguard"
	ProtocolSOCKS5      Protocol = "socks5"
	ProtocolHTTP        Protocol = "http"
	ProtocolUnknown     Protocol = "unknown"
)

// Credentials contain references only. Secret values belong in the OS credential store.
type Credentials struct {
	UsernameRef   string `json:"usernameRef,omitempty"`
	PasswordRef   string `json:"passwordRef,omitempty"`
	UUIDRef       string `json:"uuidRef,omitempty"`
	PrivateKeyRef string `json:"privateKeyRef,omitempty"`
}

type Transport struct {
	Network string `json:"network"`
	Path    string `json:"path,omitempty"`
	Host    string `json:"host,omitempty"`
}

type TLSOptions struct {
	Enabled  bool     `json:"enabled"`
	SNI      string   `json:"sni,omitempty"`
	ALPN     []string `json:"alpn,omitempty"`
	Insecure bool     `json:"insecure,omitempty"`
}

type Node struct {
	ID                string            `json:"id"`
	Name              string            `json:"name"`
	Protocol          Protocol          `json:"protocol"`
	Server            string            `json:"server"`
	Port              uint16            `json:"port"`
	Credentials       Credentials       `json:"credentials,omitempty"`
	Transport         Transport         `json:"transport"`
	TLS               TLSOptions        `json:"tls"`
	Options           map[string]string `json:"options,omitempty"`
	SourceID          string            `json:"sourceId,omitempty"`
	GroupID           string            `json:"groupId,omitempty"`
	Tags              []string          `json:"tags,omitempty"`
	SourceMetadataRef string            `json:"sourceMetadataRef,omitempty"`
	WGPublicKey       string            `json:"wgPublicKey,omitempty"`
	WGLocalAddress    string            `json:"wgLocalAddress,omitempty"`
	Cipher            string            `json:"cipher,omitempty"`
	Security          string            `json:"security,omitempty"`
	Flow              string            `json:"flow,omitempty"`
	AlterID           int               `json:"alterId,omitempty"`
	ALPN              []string          `json:"alpn,omitempty"`
}

type NodeGroup struct {
	ID   string `json:"id"`
	Name string `json:"name"`
}

type Subscription struct {
	ID                string            `json:"id"`
	Name              string            `json:"name"`
	URLSecretRef      string            `json:"urlSecretRef,omitempty"`
	Format            string            `json:"format"`
	Enabled           bool              `json:"enabled"`
	UpdateMinutes     int               `json:"updateMinutes"`
	UserAgent         string            `json:"userAgent,omitempty"`
	HeaderSecretRefs  map[string]string `json:"headerSecretRefs,omitempty"`
	LastUpdated       string            `json:"lastUpdated,omitempty"`
	LastAttempt       string            `json:"lastAttempt,omitempty"`
	LastError         string            `json:"lastError,omitempty"`
	ParseErrorCount   int               `json:"parseErrorCount,omitempty"`
	NodeCount         int               `json:"nodeCount,omitempty"`
	Sort              int               `json:"sort,omitempty"`
	RemarksFilter     string            `json:"remarksFilter,omitempty"`
	LegacyMetadataRef string            `json:"legacyMetadataRef,omitempty"`
}

type Chain struct {
	ID         string   `json:"id"`
	Name       string   `json:"name"`
	HopNodeIDs []string `json:"hopNodeIds"`
}

type PortBinding struct {
	ID         string `json:"id"`
	ChainID    string `json:"chainId"`
	ListenHost string `json:"listenHost"`
	ListenPort uint16 `json:"listenPort"`
	Remark     string `json:"remark,omitempty"`
}

type TUNBindingKind string

const (
	TUNBindingNone  TUNBindingKind = "none"
	TUNBindingNode  TUNBindingKind = "node"
	TUNBindingChain TUNBindingKind = "chain"
)

type TUNBinding struct {
	Kind     TUNBindingKind `json:"kind"`
	TargetID string         `json:"targetId,omitempty"`
	Enabled  bool           `json:"enabled"`
}

type CoreSettings struct {
	Type       string            `json:"type"`
	Executable map[string]string `json:"executables"`
	LogLevel   string            `json:"logLevel"`
}

type NetworkSettings struct {
	EnableIPv6           bool     `json:"enableIPv6"`
	EnableUDP            bool     `json:"enableUDP"`
	EnableSniffing       bool     `json:"enableSniffing"`
	AllowLAN             bool     `json:"allowLAN"`
	EnableMux            bool     `json:"enableMux"`
	AllowInsecure        bool     `json:"allowInsecure"`
	EnableFragment       bool     `json:"enableFragment"`
	EnableFinalFragment  bool     `json:"enableFinalFragment"`
	XrayFragmentPackets  string   `json:"xrayFragmentPackets,omitempty"`
	XrayFragmentLengths  []string `json:"xrayFragmentLengths,omitempty"`
	XrayFragmentDelays   []string `json:"xrayFragmentDelays,omitempty"`
	XrayFragmentMaxSplit int      `json:"xrayFragmentMaxSplit,omitempty"`
	SingboxMuxProtocol   string   `json:"singboxMuxProtocol,omitempty"`
	BlockQUIC            bool     `json:"blockQUIC"`
	RemoteDNSURL         string   `json:"remoteDNSUrl"`
	BootstrapDNS         string   `json:"bootstrapDNS"`
	SpeedPingTestURL     string   `json:"speedPingTestUrl,omitempty"`
}

type Settings struct {
	CustomNodesGroupName string          `json:"customNodesGroupName,omitempty"`
	BaseListenHost       string          `json:"baseListenHost"`
	BaseListenPort       uint16          `json:"baseListenPort"`
	Core                 CoreSettings    `json:"core"`
	Network              NetworkSettings `json:"network"`
	AutoStart            bool            `json:"autoStart"`
	RunOnStartup         bool            `json:"runOnStartup"`
	MinimizeOnStart      bool            `json:"minimizeOnStart"`
	CloseToTray          bool            `json:"closeToTray"`
	ConfigOutputDir      string          `json:"configOutputDir,omitempty"`
}

type Workspace struct {
	SchemaVersion int            `json:"schemaVersion"`
	Groups        []NodeGroup    `json:"groups"`
	Subscriptions []Subscription `json:"subscriptions"`
	Nodes         []Node         `json:"nodes"`
	Chains        []Chain        `json:"chains"`
	PortBindings  []PortBinding  `json:"portBindings"`
	ActiveNodeID  string         `json:"activeNodeId,omitempty"`
	TUN           TUNBinding     `json:"tun"`
	Settings      Settings       `json:"settings"`
}

func DefaultWorkspace() Workspace {
	return Workspace{
		SchemaVersion: 1,
		Groups:        []NodeGroup{}, Subscriptions: []Subscription{}, Nodes: []Node{}, Chains: []Chain{}, PortBindings: []PortBinding{},
		TUN: TUNBinding{Kind: TUNBindingNone},
		Settings: Settings{
			CustomNodesGroupName: "Customs",
			BaseListenHost:       "127.0.0.1", BaseListenPort: 10808,
			Core:        CoreSettings{Type: "sing-box", Executable: map[string]string{}, LogLevel: "warning"},
			Network:     NetworkSettings{EnableUDP: true, EnableSniffing: true, BlockQUIC: true, SingboxMuxProtocol: "h2mux", RemoteDNSURL: "https://cloudflare-dns.com/dns-query", BootstrapDNS: "119.29.29.29", SpeedPingTestURL: "https://www.google.com/generate_204"},
			CloseToTray: true,
		},
	}
}

func (w Workspace) Validate() error {
	if w.SchemaVersion < 1 {
		return errors.New("schemaVersion must be at least 1")
	}
	if w.Settings.BaseListenPort == 0 {
		return errors.New("base listener port must be between 1 and 65535")
	}
	switch w.Settings.Core.Type {
	case "sing-box", "xray", "mihomo":
	default:
		return fmt.Errorf("unsupported core type %q", w.Settings.Core.Type)
	}
	if w.Settings.Core.Executable == nil {
		return errors.New("core executable map must not be null")
	}
	dnsURL, err := url.Parse(w.Settings.Network.RemoteDNSURL)
	if err != nil || !strings.EqualFold(dnsURL.Scheme, "https") || dnsURL.Host == "" || dnsURL.User != nil || dnsURL.Fragment != "" {
		return errors.New("remote DNS must be an absolute HTTPS URL")
	}
	if net.ParseIP(strings.TrimSpace(w.Settings.Network.BootstrapDNS)) == nil {
		return errors.New("bootstrap DNS must be an IP address to avoid DNS bootstrap loops")
	}
	if net.ParseIP(w.Settings.BaseListenHost) == nil && !strings.EqualFold(w.Settings.BaseListenHost, "localhost") {
		return errors.New("base listener host must be a valid IP address")
	}
	if !w.Settings.Network.AllowLAN && !isLoopbackHost(w.Settings.BaseListenHost) {
		return errors.New("Base listener must use a loopback address while Allow LAN is disabled")
	}
	if w.Settings.Network.SingboxMuxProtocol != "" && w.Settings.Network.SingboxMuxProtocol != "smux" && w.Settings.Network.SingboxMuxProtocol != "h2mux" && w.Settings.Network.SingboxMuxProtocol != "yamux" {
		return fmt.Errorf("unsupported sing-box mux protocol %q", w.Settings.Network.SingboxMuxProtocol)
	}
	if w.Settings.Network.XrayFragmentMaxSplit < 0 || int64(w.Settings.Network.XrayFragmentMaxSplit) > 2147483647 {
		return errors.New("Xray fragment max split must be between 0 and 2147483647")
	}
	if w.Settings.Network.EnableFragment || w.Settings.Network.EnableFinalFragment {
		packets := strings.TrimSpace(w.Settings.Network.XrayFragmentPackets)
		if packets == "" {
			packets = "tlshello"
		}
		if packets != "tlshello" {
			if err := validateIntegerRange("Xray fragment packets", packets, 1); err != nil {
				return err
			}
		}
		lengths := w.Settings.Network.XrayFragmentLengths
		if len(lengths) == 0 {
			lengths = []string{"50-100"}
		}
		for _, value := range lengths {
			if err := validateIntegerRange("Xray fragment length", value, 1); err != nil {
				return err
			}
		}
		delays := w.Settings.Network.XrayFragmentDelays
		if len(delays) == 0 {
			delays = []string{"10-20"}
		}
		for _, value := range delays {
			if err := validateIntegerRange("Xray fragment delay", value, 0); err != nil {
				return err
			}
		}
	}
	subscriptionIDs := make(map[string]bool, len(w.Subscriptions))
	for _, subscription := range w.Subscriptions {
		if strings.TrimSpace(subscription.ID) == "" || strings.TrimSpace(subscription.Name) == "" {
			return errors.New("subscription ID and name are required")
		}
		if subscriptionIDs[subscription.ID] {
			return fmt.Errorf("duplicate subscription ID %q", subscription.ID)
		}
		subscriptionIDs[subscription.ID] = true
	}
	groupIDs := make(map[string]bool, len(w.Groups))
	groupNames := make(map[string]bool, len(w.Groups))
	for _, group := range w.Groups {
		name := strings.ToLower(strings.TrimSpace(group.Name))
		if strings.TrimSpace(group.ID) == "" || name == "" {
			return errors.New("node group ID and name are required")
		}
		if groupIDs[group.ID] || groupNames[name] {
			return fmt.Errorf("duplicate node group ID or name %q", group.Name)
		}
		groupIDs[group.ID], groupNames[name] = true, true
	}

	nodes := make(map[string]Node, len(w.Nodes))
	for _, node := range w.Nodes {
		if strings.TrimSpace(node.ID) == "" {
			return errors.New("node ID is required")
		}
		if _, exists := nodes[node.ID]; exists {
			return fmt.Errorf("duplicate node ID %q", node.ID)
		}
		if strings.TrimSpace(node.Name) == "" {
			return fmt.Errorf("node %q name is required", node.ID)
		}
		switch node.Protocol {
		case ProtocolVMess, ProtocolVLESS, ProtocolTrojan, ProtocolShadowsocks, ProtocolWireGuard, ProtocolSOCKS5, ProtocolHTTP, ProtocolUnknown:
		default:
			return fmt.Errorf("node %q has unsupported protocol %q", node.ID, node.Protocol)
		}
		if strings.TrimSpace(node.Server) == "" || node.Port == 0 {
			return fmt.Errorf("node %q has an invalid endpoint", node.ID)
		}
		if node.GroupID != "" && !groupIDs[node.GroupID] && !subscriptionIDs[node.GroupID] {
			return fmt.Errorf("node %q references missing group %q", node.ID, node.GroupID)
		}
		nodes[node.ID] = node
	}

	chains := make(map[string]Chain, len(w.Chains))
	for _, chain := range w.Chains {
		if strings.TrimSpace(chain.ID) == "" {
			return errors.New("chain ID is required")
		}
		if _, exists := chains[chain.ID]; exists {
			return fmt.Errorf("duplicate chain ID %q", chain.ID)
		}
		if strings.TrimSpace(chain.Name) == "" || len(chain.HopNodeIDs) == 0 {
			return fmt.Errorf("chain %q requires a name and at least one hop", chain.ID)
		}
		hopSeen := map[string]bool{}
		for _, nodeID := range chain.HopNodeIDs {
			if hopSeen[nodeID] {
				return fmt.Errorf("chain %q repeats node %q", chain.ID, nodeID)
			}
			hopSeen[nodeID] = true
			if _, ok := nodes[nodeID]; !ok {
				return fmt.Errorf("chain %q references missing node %q", chain.ID, nodeID)
			}
		}
		chains[chain.ID] = chain
	}

	ports := map[uint16]string{w.Settings.BaseListenPort: "base"}
	boundChains := make(map[string]bool, len(w.PortBindings))
	bindingIDs := make(map[string]bool, len(w.PortBindings))
	for _, binding := range w.PortBindings {
		if strings.TrimSpace(binding.ID) == "" {
			return errors.New("port binding ID is required")
		}
		if bindingIDs[binding.ID] {
			return fmt.Errorf("duplicate port binding ID %q", binding.ID)
		}
		bindingIDs[binding.ID] = true
		if binding.ListenPort == 0 {
			return fmt.Errorf("port binding %q has invalid port", binding.ID)
		}
		if net.ParseIP(binding.ListenHost) == nil && !strings.EqualFold(binding.ListenHost, "localhost") {
			return fmt.Errorf("port binding %q has invalid listen host", binding.ID)
		}
		if !w.Settings.Network.AllowLAN && !isLoopbackHost(binding.ListenHost) {
			return fmt.Errorf("port binding %q exposes a non-loopback listener while Allow LAN is disabled", binding.ID)
		}
		if _, ok := chains[binding.ChainID]; !ok {
			return fmt.Errorf("port binding %q references missing chain %q", binding.ID, binding.ChainID)
		}
		if boundChains[binding.ChainID] {
			return fmt.Errorf("chain %q has more than one local port binding", binding.ChainID)
		}
		if owner, exists := ports[binding.ListenPort]; exists {
			return fmt.Errorf("port %d is shared by %s and chain %s", binding.ListenPort, owner, binding.ChainID)
		}
		ports[binding.ListenPort] = "chain " + binding.ChainID
		boundChains[binding.ChainID] = true
	}
	for chainID := range chains {
		if !boundChains[chainID] {
			return fmt.Errorf("chain %q has no local port binding", chainID)
		}
	}

	if w.ActiveNodeID != "" {
		if _, ok := nodes[w.ActiveNodeID]; !ok {
			return fmt.Errorf("active Base Node %q does not exist", w.ActiveNodeID)
		}
	}
	switch w.TUN.Kind {
	case TUNBindingNone:
		if w.TUN.Enabled {
			return errors.New("TUN cannot be enabled without a target binding")
		}
		if w.TUN.TargetID != "" {
			return errors.New("unbound TUN must not have a target ID")
		}
	case TUNBindingNode:
		if _, ok := nodes[w.TUN.TargetID]; !ok {
			return fmt.Errorf("TUN Base Node %q does not exist", w.TUN.TargetID)
		}
	case TUNBindingChain:
		if _, ok := chains[w.TUN.TargetID]; !ok {
			return fmt.Errorf("TUN Chain %q does not exist", w.TUN.TargetID)
		}
	default:
		return fmt.Errorf("unsupported TUN binding kind %q", w.TUN.Kind)
	}
	return nil
}

func isLoopbackHost(value string) bool {
	if strings.EqualFold(value, "localhost") {
		return true
	}
	ip := net.ParseIP(value)
	return ip != nil && ip.IsLoopback()
}

func validateIntegerRange(name, value string, minimum int) error {
	parts := strings.Split(value, "-")
	if len(parts) > 2 {
		return fmt.Errorf("%s range %q is invalid", name, value)
	}
	first, err := strconv.Atoi(strings.TrimSpace(parts[0]))
	if err != nil || first < minimum {
		return fmt.Errorf("%s range %q must contain non-negative values", name, value)
	}
	if len(parts) == 2 {
		last, parseErr := strconv.Atoi(strings.TrimSpace(parts[1]))
		if parseErr != nil || last < minimum || last < first {
			return fmt.Errorf("%s range %q has invalid bounds", name, value)
		}
	}
	return nil
}
