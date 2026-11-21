package service

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"strconv"
	"testing"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/core"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"gopkg.in/yaml.v3"
)

func TestNodeTestWorkspaceCreatesOneMixedListenerPerNode(t *testing.T) {
	workspace := domain.DefaultWorkspace()
	nodes := []domain.Node{
		{ID: "one", Name: "One", Protocol: domain.ProtocolSOCKS5, Server: "one.example", Port: 1080},
		{ID: "two", Name: "Two", Protocol: domain.ProtocolSOCKS5, Server: "two.example", Port: 1081},
	}
	testWorkspace := buildNodeTestWorkspace(workspace, nodes, []uint16{21001, 21002})
	if testWorkspace.ActiveNodeID != "" || testWorkspace.TUN.Enabled || testWorkspace.TUN.Kind != domain.TUNBindingNone {
		t.Fatalf("temporary test workspace must not inherit active/TUN routing: %+v", testWorkspace)
	}
	if len(testWorkspace.Nodes) != 2 || len(testWorkspace.Chains) != 2 || len(testWorkspace.PortBindings) != 2 {
		t.Fatalf("expected one node, chain and local listener per test target: %+v", testWorkspace)
	}
	for _, coreName := range []string{"sing-box", "xray", "mihomo"} {
		testWorkspace.Settings.Core.Type = coreName
		generated, err := core.GenerateConfig(context.Background(), testWorkspace, coreName, nil)
		if err != nil {
			t.Fatalf("generate multi-node %s test config: %v", coreName, err)
		}
		var config map[string]any
		if coreName == "mihomo" {
			if err := yaml.Unmarshal(generated.Data, &config); err != nil {
				t.Fatal(err)
			}
			listeners, ok := config["listeners"].([]any)
			if !ok || len(listeners) != 2 {
				t.Fatalf("expected two Mihomo mixed listeners, got %#v", config["listeners"])
			}
			for _, listener := range listeners {
				if listener.(map[string]any)["type"] != "mixed" {
					t.Fatalf("Mihomo node-test listener is not mixed: %+v", listener)
				}
			}
			continue
		}
		if err := json.Unmarshal(generated.Data, &config); err != nil {
			t.Fatal(err)
		}
		inbounds, ok := config["inbounds"].([]any)
		if !ok || len(inbounds) != 2 {
			t.Fatalf("expected two %s mixed listeners, got %#v", coreName, config["inbounds"])
		}
		for _, inbound := range inbounds {
			value := inbound.(map[string]any)
			if coreName == "xray" && value["protocol"] != "mixed" {
				t.Fatalf("Xray node-test inbound must be mixed: %+v", value)
			}
			if coreName == "sing-box" && value["type"] != "mixed" {
				t.Fatalf("sing-box node-test inbound must be mixed: %+v", value)
			}
		}
	}
}

func TestNodeTCPPingMeasuresReachableTCPEndpoint(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		connection, acceptErr := listener.Accept()
		if acceptErr == nil {
			_ = connection.Close()
		}
	}()
	host, portText, err := net.SplitHostPort(listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	var port uint16
	if _, err := fmt.Sscanf(portText, "%d", &port); err != nil {
		t.Fatal(err)
	}
	delay, err := testNodeTCPPing(context.Background(), domain.Node{ID: "local", Name: "Local", Server: host, Port: port})
	if err != nil {
		t.Fatalf("TCP ping should reach local listener: %v", err)
	}
	if delay < 0 {
		t.Fatalf("TCP ping returned negative delay: %s", delay)
	}
}

func TestNodeTCPPingHonoursCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err := testNodeTCPPing(ctx, domain.Node{ID: "unreachable", Name: "Unreachable", Server: "192.0.2.1", Port: 65000})
	if err == nil {
		t.Fatal("cancelled TCP ping should fail")
	}
}

func TestNodeTestURLUsesV2RayNDefaultAndValidatesOverrides(t *testing.T) {
	value, err := nodeTestURL("")
	if err != nil {
		t.Fatal(err)
	}
	if value != "https://www.google.com/generate_204" {
		t.Fatalf("unexpected default test URL %q", value)
	}
	value, err = nodeTestURL("https://example.com/ping")
	if err != nil || value != "https://example.com/ping" {
		t.Fatalf("valid custom URL rejected: %q %v", value, err)
	}
	for _, invalid := range []string{"ftp://example.com/ping", "not a URL", "https:///missing-host"} {
		if _, err := nodeTestURL(invalid); err == nil {
			t.Fatalf("invalid test URL %q should be rejected", invalid)
		}
	}
}

func TestSOCKS5DialerConnectsThroughNoAuthListener(t *testing.T) {
	target, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer target.Close()
	targetAccepted := make(chan net.Conn, 1)
	go func() {
		connection, acceptErr := target.Accept()
		if acceptErr == nil {
			targetAccepted <- connection
		}
	}()
	proxy, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer proxy.Close()
	go func() {
		client, acceptErr := proxy.Accept()
		if acceptErr != nil {
			return
		}
		defer client.Close()
		greeting := make([]byte, 3)
		if _, err := io.ReadFull(client, greeting); err != nil {
			return
		}
		_, _ = client.Write([]byte{5, 0})
		header := make([]byte, 4)
		if _, err := io.ReadFull(client, header); err != nil {
			return
		}
		var host string
		switch header[3] {
		case 1:
			address := make([]byte, 4)
			if _, err := io.ReadFull(client, address); err != nil {
				return
			}
			host = net.IP(address).String()
		case 4:
			address := make([]byte, 16)
			if _, err := io.ReadFull(client, address); err != nil {
				return
			}
			host = net.IP(address).String()
		case 3:
			size := []byte{0}
			if _, err := io.ReadFull(client, size); err != nil {
				return
			}
			address := make([]byte, int(size[0]))
			if _, err := io.ReadFull(client, address); err != nil {
				return
			}
			host = string(address)
		default:
			return
		}
		portBytes := make([]byte, 2)
		if _, err := io.ReadFull(client, portBytes); err != nil {
			return
		}
		destination := net.JoinHostPort(host, strconv.Itoa(int(portBytes[0])<<8|int(portBytes[1])))
		remote, dialErr := net.Dial("tcp", destination)
		if dialErr != nil {
			_, _ = client.Write([]byte{5, 5, 0, 1, 0, 0, 0, 0, 0, 0})
			return
		}
		defer remote.Close()
		_, _ = client.Write([]byte{5, 0, 0, 1, 0, 0, 0, 0, 0, 0})
		go func() { _, _ = io.Copy(remote, client) }()
		_, _ = io.Copy(client, remote)
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	connection, err := dialSOCKS5Context(ctx, proxy.Addr().String(), target.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	if _, err := connection.Write([]byte("hello")); err != nil {
		t.Fatal(err)
	}
	select {
	case accepted := <-targetAccepted:
		defer accepted.Close()
		buffer := make([]byte, 5)
		if _, err := io.ReadFull(accepted, buffer); err != nil {
			t.Fatal(err)
		}
		if string(buffer) != "hello" {
			t.Fatalf("unexpected forwarded payload %q", buffer)
		}
	case <-ctx.Done():
		t.Fatal("SOCKS5 target did not receive forwarded connection")
	}
}

func TestDeleteNodesIsAtomicAndClearsActiveTUNReferences(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{
		{ID: "one", Name: "One", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080},
		{ID: "two", Name: "Two", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1081},
		{ID: "three", Name: "Three", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1082},
	}
	w.ActiveNodeID = "one"
	w.TUN = domain.TUNBinding{Kind: domain.TUNBindingNode, TargetID: "one", Enabled: true}
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.DeleteNodes([]string{"one", "missing"}); err == nil {
		t.Fatal("deleting a batch containing a missing ID should fail")
	}
	if len(service.GetWorkspace().Nodes) != 3 {
		t.Fatal("failed batch deletion must not partially modify the workspace")
	}
	updated, err := service.DeleteNodes([]string{"one", "two", "one"})
	if err != nil {
		t.Fatal(err)
	}
	if len(updated.Nodes) != 1 || updated.Nodes[0].ID != "three" {
		t.Fatalf("unexpected remaining nodes: %+v", updated.Nodes)
	}
	if updated.ActiveNodeID != "" || updated.TUN.Kind != domain.TUNBindingNone || updated.TUN.Enabled {
		t.Fatalf("active node/TUN references were not cleared: %+v", updated)
	}
}

func TestDeleteNodesRejectsBatchWhenAnyNodeBelongsToChain(t *testing.T) {
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "chain-node", Name: "Chain Node", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080}, {ID: "free-node", Name: "Free Node", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1081}}
	w.Chains = []domain.Chain{{ID: "chain", Name: "Protected Chain", HopNodeIDs: []string{"chain-node"}}}
	w.PortBindings = []domain.PortBinding{{ID: "binding", ChainID: "chain", ListenHost: "127.0.0.1", ListenPort: 20001}}
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.DeleteNodes([]string{"free-node", "chain-node"}); err == nil {
		t.Fatal("batch containing a Chain-referenced node must be rejected")
	}
	if len(service.GetWorkspace().Nodes) != 2 {
		t.Fatal("failed protected batch must not partially delete the free node")
	}
}

func TestStartNodeTCPPingPublishesResultsForSelectedNodes(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		for {
			connection, acceptErr := listener.Accept()
			if acceptErr != nil {
				return
			}
			_ = connection.Close()
		}
	}()
	host, portText, _ := net.SplitHostPort(listener.Addr().String())
	var port uint16
	_, _ = fmt.Sscanf(portText, "%d", &port)
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "test-node", Name: "Test", Protocol: domain.ProtocolSOCKS5, Server: host, Port: port}}
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	events := make(chan NodeTestResult, 4)
	ConfigureNodeTestEvents(service, func(result NodeTestResult) { events <- result })
	if err := service.TestNodesTCPPing([]string{"test-node"}); err != nil {
		t.Fatal(err)
	}
	select {
	case result := <-events:
		if result.Status != "testing" {
			t.Fatalf("expected pending event, got %+v", result)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for pending test event")
	}
	select {
	case result := <-events:
		if result.Status != "success" || result.TestType != NodeTestTCPPing {
			t.Fatalf("unexpected TCP ping result: %+v", result)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for TCP ping result")
	}
}

func TestRealDelayAlsoPublishesDirectTCPPingResults(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		for {
			connection, acceptErr := listener.Accept()
			if acceptErr != nil {
				return
			}
			_ = connection.Close()
		}
	}()
	host, portText, _ := net.SplitHostPort(listener.Addr().String())
	var port uint16
	_, _ = fmt.Sscanf(portText, "%d", &port)
	w := domain.DefaultWorkspace()
	w.Settings.Core.Executable["sing-box"] = "/definitely-not-installed/chainport-sing-box"
	w.Nodes = []domain.Node{{ID: "test-node", Name: "Test", Protocol: domain.ProtocolSOCKS5, Server: host, Port: port}}
	service, err := NewWorkspaceServiceWithStore(context.Background(), &memoryStore{workspace: w})
	if err != nil {
		t.Fatal(err)
	}
	events := make(chan NodeTestResult, 8)
	ConfigureNodeTestEvents(service, func(result NodeTestResult) { events <- result })
	if err := service.TestNodesRealDelay([]string{"test-node"}); err != nil {
		t.Fatal(err)
	}
	deadline := time.After(3 * time.Second)
	gotTCPPing := false
	gotRealDelayFailure := false
	for !gotTCPPing || !gotRealDelayFailure {
		select {
		case result := <-events:
			if result.TestType == NodeTestTCPPing && result.Status == "success" {
				gotTCPPing = true
			}
			if result.TestType == NodeTestRealDelay && result.Status == "failed" {
				gotRealDelayFailure = true
			}
		case <-deadline:
			t.Fatalf("timed out waiting for TCP Ping and Real Delay events: tcpPing=%v realDelayFailure=%v", gotTCPPing, gotRealDelayFailure)
		}
	}
	results := service.GetNodeTestResults()
	found := false
	for _, result := range results {
		if result.NodeID == "test-node" && result.TestType == NodeTestTCPPing && result.Status == "success" && result.DelayMS >= 0 {
			found = true
		}
	}
	if !found {
		t.Fatalf("Real Delay did not persist the direct TCP Ping result: %+v", results)
	}
}
