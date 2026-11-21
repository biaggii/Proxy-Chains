package service

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/core"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	runtimecore "github.com/biaggii/Proxy-Chains/go-wails3/internal/runtime"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
)

const (
	NodeTestTCPPing          = "tcp-ping"
	NodeTestRealDelay        = "real-delay"
	nodeTestBatchSize        = 10
	nodeTestConcurrency      = 10
	nodeTestTCPPingTimeout   = 5 * time.Second
	nodeTestRealDelayTimeout = 10 * time.Second
	defaultNodeTestURL       = "https://www.google.com/generate_204"
)

type NodeTestResult struct {
	NodeID    string    `json:"nodeId"`
	TestType  string    `json:"testType"`
	Status    string    `json:"status"`
	DelayMS   int64     `json:"delayMs"`
	Error     string    `json:"error,omitempty"`
	UpdatedAt time.Time `json:"updatedAt"`
}

type nodeTestBatchRetryError struct{ err error }

func (e *nodeTestBatchRetryError) Error() string { return e.err.Error() }
func (e *nodeTestBatchRetryError) Unwrap() error { return e.err }

func ConfigureNodeTestEvents(s *WorkspaceService, emit func(NodeTestResult)) {
	s.testMu.Lock()
	defer s.testMu.Unlock()
	s.testEmitter = emit
	if s.testResults == nil {
		s.testResults = map[string]NodeTestResult{}
	}
}

func (s *WorkspaceService) GetNodeTestResults() []NodeTestResult {
	s.testMu.Lock()
	defer s.testMu.Unlock()
	results := make([]NodeTestResult, 0, len(s.testResults))
	for _, result := range s.testResults {
		results = append(results, result)
	}
	return results
}

func (s *WorkspaceService) TestNodesTCPPing(nodeIDs []string) error {
	return s.startNodeTests(nodeIDs, NodeTestTCPPing)
}

func (s *WorkspaceService) TestNodesRealDelay(nodeIDs []string) error {
	return s.startNodeTests(nodeIDs, NodeTestRealDelay)
}

func (s *WorkspaceService) CancelNodeTests() {
	s.testMu.Lock()
	s.markPendingNodeTestsCancelledLocked("Test cancelled")
	s.testRunID++
	cancel := s.testCancel
	s.testCancel = nil
	s.testMu.Unlock()
	if cancel != nil {
		cancel()
	}
}

func (s *WorkspaceService) startNodeTests(nodeIDs []string, testType string) error {
	if testType != NodeTestTCPPing && testType != NodeTestRealDelay {
		return errors.New("unsupported node test")
	}
	unique := make([]string, 0, len(nodeIDs))
	seen := map[string]bool{}
	for _, id := range nodeIDs {
		id = strings.TrimSpace(id)
		if id != "" && !seen[id] {
			seen[id] = true
			unique = append(unique, id)
		}
	}
	if len(unique) == 0 {
		return errors.New("select at least one Base Node to test")
	}
	s.mu.RLock()
	workspace := cloneWorkspace(s.state)
	secrets := s.secrets
	s.mu.RUnlock()
	nodes := make([]domain.Node, 0, len(unique))
	for _, id := range unique {
		found := false
		for _, node := range workspace.Nodes {
			if node.ID == id {
				nodes = append(nodes, node)
				found = true
				break
			}
		}
		if !found {
			return fmt.Errorf("Base Node %q no longer exists", id)
		}
	}
	s.testMu.Lock()
	if s.testCancel != nil {
		s.markPendingNodeTestsCancelledLocked("Superseded by a new test")
		s.testCancel()
	}
	s.testRunID++
	runID := s.testRunID
	var ctx context.Context
	var cancel context.CancelFunc
	if s.appContext != nil {
		ctx, cancel = context.WithCancel(s.appContext)
	} else {
		ctx, cancel = context.WithCancel(context.Background())
	}
	s.testCancel = cancel
	if s.testResults == nil {
		s.testResults = map[string]NodeTestResult{}
	}
	for _, node := range nodes {
		if testType == NodeTestRealDelay {
			s.publishNodeTestLocked(NodeTestResult{NodeID: node.ID, TestType: NodeTestTCPPing, Status: "testing", UpdatedAt: time.Now().UTC()})
		}
		s.publishNodeTestLocked(NodeTestResult{NodeID: node.ID, TestType: testType, Status: "testing", UpdatedAt: time.Now().UTC()})
	}
	s.testMu.Unlock()

	go func() {
		defer func() {
			cancel()
			s.testMu.Lock()
			if s.testRunID == runID {
				s.testCancel = nil
			}
			s.testMu.Unlock()
		}()
		if testType == NodeTestTCPPing {
			runTCPPingTests(ctx, nodes, func(result NodeTestResult) { s.publishNodeTestForRun(runID, result) })
			return
		}
		// A Real Delay run also refreshes the direct TCP endpoint latency so
		// both measurements are visible together in the Base Node table.
		runTCPPingTests(ctx, nodes, func(result NodeTestResult) { s.publishNodeTestForRun(runID, result) })
		if ctx.Err() != nil {
			return
		}
		for start := 0; start < len(nodes); start += nodeTestBatchSize {
			if ctx.Err() != nil {
				return
			}
			end := min(start+nodeTestBatchSize, len(nodes))
			results, err := testNodesRealDelayBatch(ctx, workspace, nodes[start:end], secrets)
			var retryErr *nodeTestBatchRetryError
			if errors.As(err, &retryErr) {
				results, err = testNodesRealDelayWithFallback(ctx, workspace, nodes[start:end], secrets)
			}
			if err != nil {
				for index, node := range nodes[start:end] {
					var result NodeTestResult
					if index < len(results) && results[index].Status != "" {
						result = results[index]
					} else {
						result = failedNodeTest(node.ID, NodeTestRealDelay, err)
					}
					s.publishNodeTestForRun(runID, result)
				}
			} else {
				for _, result := range results {
					s.publishNodeTestForRun(runID, result)
				}
			}
			if end < len(nodes) {
				select {
				case <-ctx.Done():
					return
				case <-time.After(time.Second):
				}
			}
		}
	}()
	return nil
}

func testNodesRealDelayWithFallback(ctx context.Context, workspace domain.Workspace, nodes []domain.Node, secrets security.SecretStore) ([]NodeTestResult, error) {
	results, err := testNodesRealDelayBatch(ctx, workspace, nodes, secrets)
	if err == nil {
		return results, nil
	}
	var retryErr *nodeTestBatchRetryError
	if !errors.As(err, &retryErr) {
		return nil, err
	}
	if len(nodes) == 1 {
		return []NodeTestResult{failedNodeTest(nodes[0].ID, NodeTestRealDelay, err)}, nil
	}
	middle := len(nodes) / 2
	left, leftErr := testNodesRealDelayWithFallback(ctx, workspace, nodes[:middle], secrets)
	right, rightErr := testNodesRealDelayWithFallback(ctx, workspace, nodes[middle:], secrets)
	if leftErr != nil {
		for _, node := range nodes[:middle] {
			left = append(left, failedNodeTest(node.ID, NodeTestRealDelay, leftErr))
		}
	}
	if rightErr != nil {
		for _, node := range nodes[middle:] {
			right = append(right, failedNodeTest(node.ID, NodeTestRealDelay, rightErr))
		}
	}
	return append(left, right...), nil
}

func (s *WorkspaceService) markPendingNodeTestsCancelledLocked(reason string) {
	for key, result := range s.testResults {
		if result.Status != "testing" {
			continue
		}
		result.Status = "cancelled"
		result.DelayMS = -1
		result.Error = reason
		result.UpdatedAt = time.Now().UTC()
		s.testResults[key] = result
		if s.testEmitter != nil {
			s.testEmitter(result)
		}
	}
}

func failedNodeTest(nodeID, testType string, err error) NodeTestResult {
	result := NodeTestResult{NodeID: nodeID, TestType: testType, Status: "failed", DelayMS: -1, UpdatedAt: time.Now().UTC()}
	if err != nil {
		result.Error = err.Error()
		if errors.Is(err, context.Canceled) {
			result.Status = "cancelled"
		}
	}
	return result
}

func runTCPPingTests(ctx context.Context, nodes []domain.Node, publish func(NodeTestResult)) {
	completed := make(map[string]bool, len(nodes))
	var completedMu sync.Mutex
	for start := 0; start < len(nodes); start += nodeTestBatchSize {
		if ctx.Err() != nil {
			break
		}
		end := min(start+nodeTestBatchSize, len(nodes))
		batch := nodes[start:end]
		jobs := make(chan domain.Node)
		var group sync.WaitGroup
		for i := 0; i < len(batch); i++ {
			group.Add(1)
			go func() {
				defer group.Done()
				for node := range jobs {
					delay, err := testNodeTCPPing(ctx, node)
					result := NodeTestResult{NodeID: node.ID, TestType: NodeTestTCPPing, Status: "success", DelayMS: delay.Milliseconds(), UpdatedAt: time.Now().UTC()}
					if err != nil {
						result = failedNodeTest(node.ID, NodeTestTCPPing, err)
					}
					publish(result)
					completedMu.Lock()
					completed[node.ID] = true
					completedMu.Unlock()
				}
			}()
		}
		cancelled := false
		for _, node := range batch {
			select {
			case jobs <- node:
			case <-ctx.Done():
				cancelled = true
			}
			if cancelled {
				break
			}
		}
		close(jobs)
		group.Wait()
		if cancelled || ctx.Err() != nil {
			break
		}
		if end < len(nodes) {
			select {
			case <-ctx.Done():
				cancelled = true
			case <-time.After(time.Second):
			}
			if cancelled {
				break
			}
		}
	}
	if ctx.Err() != nil {
		for _, node := range nodes {
			completedMu.Lock()
			done := completed[node.ID]
			completedMu.Unlock()
			if !done {
				publish(failedNodeTest(node.ID, NodeTestTCPPing, ctx.Err()))
			}
		}
	}
}

func (s *WorkspaceService) publishNodeTestForRun(runID uint64, result NodeTestResult) {
	s.testMu.Lock()
	defer s.testMu.Unlock()
	if s.testRunID != runID {
		return
	}
	s.publishNodeTestLocked(result)
}

func (s *WorkspaceService) publishNodeTestLocked(result NodeTestResult) {
	key := result.NodeID + ":" + result.TestType
	s.testResults[key] = result
	emit := s.testEmitter
	if emit != nil {
		emit(result)
	}
}

func testNodeTCPPing(ctx context.Context, node domain.Node) (time.Duration, error) {
	if strings.TrimSpace(node.Server) == "" || node.Port == 0 {
		return 0, errors.New("node endpoint is empty")
	}
	var addressIP net.IP
	if parsed := net.ParseIP(node.Server); parsed != nil {
		addressIP = parsed
	} else {
		addresses, err := net.DefaultResolver.LookupIPAddr(ctx, node.Server)
		if err != nil {
			return 0, fmt.Errorf("DNS lookup failed: %w", err)
		}
		if len(addresses) == 0 {
			return 0, errors.New("DNS lookup returned no addresses")
		}
		addressIP = addresses[0].IP
	}
	address := net.JoinHostPort(addressIP.String(), strconv.Itoa(int(node.Port)))
	connectCtx, cancel := context.WithTimeout(ctx, nodeTestTCPPingTimeout)
	defer cancel()
	started := time.Now()
	connection, err := (&net.Dialer{}).DialContext(connectCtx, "tcp", address)
	if err != nil {
		return 0, fmt.Errorf("TCP connect failed: %w", err)
	}
	delay := time.Since(started)
	_ = connection.Close()
	return delay, nil
}

func testNodesRealDelayBatch(parent context.Context, workspace domain.Workspace, nodes []domain.Node, secrets security.SecretStore) ([]NodeTestResult, error) {
	if len(nodes) == 0 {
		return nil, errors.New("no nodes to test")
	}
	batchTimeout := 35*time.Second + time.Duration((len(nodes)+nodeTestConcurrency-1)/nodeTestConcurrency)*nodeTestRealDelayTimeout
	ctx, cancel := context.WithTimeout(parent, batchTimeout)
	defer cancel()
	testURL, err := nodeTestURL(workspace.Settings.Network.SpeedPingTestURL)
	if err != nil {
		return nil, err
	}
	if secrets == nil {
		for _, node := range nodes {
			if node.Credentials.UsernameRef != "" || node.Credentials.PasswordRef != "" || node.Credentials.UUIDRef != "" || node.Credentials.PrivateKeyRef != "" || node.SourceMetadataRef != "" {
				return nil, errors.New("credential vault is unavailable for this node test")
			}
		}
	}
	ports, err := allocateNodeTestPorts(len(nodes), workspace.Settings.BaseListenPort)
	if err != nil {
		return nil, err
	}
	results := make([]NodeTestResult, len(nodes))
	resultIndex := make(map[string]int, len(nodes))
	for index, node := range nodes {
		resultIndex[node.ID] = index
	}
	testWorkspace := buildNodeTestWorkspace(workspace, nodes, ports)
	generated, err := core.GenerateConfig(ctx, testWorkspace, testWorkspace.Settings.Core.Type, secrets)
	if err != nil && len(nodes) > 1 {
		validNodes := make([]domain.Node, 0, len(nodes))
		validPorts := make([]uint16, 0, len(nodes))
		for index, node := range nodes {
			singleWorkspace := buildNodeTestWorkspace(workspace, []domain.Node{node}, []uint16{ports[index]})
			if _, singleErr := core.GenerateConfig(ctx, singleWorkspace, singleWorkspace.Settings.Core.Type, secrets); singleErr != nil {
				results[index] = failedNodeTest(node.ID, NodeTestRealDelay, fmt.Errorf("node config is not supported by the selected core: %w", singleErr))
				continue
			}
			validNodes = append(validNodes, node)
			validPorts = append(validPorts, ports[index])
		}
		if len(validNodes) == 0 {
			return results, nil
		}
		nodes, ports = validNodes, validPorts
		testWorkspace = buildNodeTestWorkspace(workspace, nodes, ports)
		generated, err = core.GenerateConfig(ctx, testWorkspace, testWorkspace.Settings.Core.Type, secrets)
	}
	if err != nil {
		return results, &nodeTestBatchRetryError{err: fmt.Errorf("generate temporary test config: %w", err)}
	}
	directory, err := os.MkdirTemp("", "chainport-node-test-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(directory)
	configPath, err := runtimecore.WriteConfig(directory, "test"+generated.Extension, generated.Data)
	if err != nil {
		return nil, err
	}
	coreName := strings.ToLower(testWorkspace.Settings.Core.Type)
	executable := testWorkspace.Settings.Core.Executable[coreName]
	if executable == "" {
		executable = testWorkspace.Settings.Core.Executable[testWorkspace.Settings.Core.Type]
	}
	if executable == "" {
		executable = coreName
	}
	executable, err = exec.LookPath(executable)
	if err != nil {
		return nil, fmt.Errorf("cannot locate %s executable: %w", coreName, err)
	}
	checkCommand, startCommand, err := coreCommands(coreName, executable, configPath)
	if err != nil {
		return nil, err
	}
	checkCtx, checkCancel := context.WithTimeout(ctx, 8*time.Second)
	check := exec.CommandContext(checkCtx, checkCommand[0], checkCommand[1:]...)
	output, checkErr := check.CombinedOutput()
	checkCancel()
	if checkErr != nil {
		return nil, &nodeTestBatchRetryError{err: fmt.Errorf("temporary core config validation failed: %s", strings.TrimSpace(string(output)))}
	}
	command := exec.CommandContext(ctx, startCommand[0], startCommand[1:]...)
	if err := command.Start(); err != nil {
		return nil, &nodeTestBatchRetryError{err: fmt.Errorf("start temporary core: %w", err)}
	}
	wait := make(chan error, 1)
	go func() { wait <- command.Wait() }()
	defer func() {
		if command.Process != nil {
			_ = command.Process.Kill()
		}
		select {
		case <-wait:
		case <-time.After(2 * time.Second):
		}
	}()
	if err := waitForNodeTestListeners(ctx, ports, wait); err != nil {
		return nil, &nodeTestBatchRetryError{err: err}
	}
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-time.After(time.Second):
	}

	jobs := make(chan int)
	var group sync.WaitGroup
	for i := 0; i < min(nodeTestConcurrency, len(nodes)); i++ {
		group.Add(1)
		go func() {
			defer group.Done()
			for index := range jobs {
				node := nodes[index]
				delay, testErr := measureV2RayRealDelay(ctx, ports[index], testURL)
				result := NodeTestResult{NodeID: node.ID, TestType: NodeTestRealDelay, Status: "success", DelayMS: delay.Milliseconds(), UpdatedAt: time.Now().UTC()}
				if testErr != nil {
					result = failedNodeTest(node.ID, NodeTestRealDelay, testErr)
				}
				results[resultIndex[node.ID]] = result
			}
		}()
	}
	for index := range nodes {
		select {
		case jobs <- index:
		case <-ctx.Done():
			close(jobs)
			group.Wait()
			return results, ctx.Err()
		}
	}
	close(jobs)
	group.Wait()
	return results, nil
}

func buildNodeTestWorkspace(workspace domain.Workspace, nodes []domain.Node, ports []uint16) domain.Workspace {
	testWorkspace := cloneWorkspace(workspace)
	testWorkspace.Nodes = append([]domain.Node(nil), nodes...)
	testWorkspace.Chains = make([]domain.Chain, 0, len(nodes))
	testWorkspace.PortBindings = make([]domain.PortBinding, 0, len(nodes))
	testWorkspace.ActiveNodeID = ""
	testWorkspace.TUN = domain.TUNBinding{Kind: domain.TUNBindingNone}
	for index, node := range nodes {
		chainID := fmt.Sprintf("node-test-%d", index+1)
		testWorkspace.Chains = append(testWorkspace.Chains, domain.Chain{ID: chainID, Name: "Node test " + node.Name, HopNodeIDs: []string{node.ID}})
		testWorkspace.PortBindings = append(testWorkspace.PortBindings, domain.PortBinding{ID: "node-test-binding-" + strconv.Itoa(index+1), ChainID: chainID, ListenHost: "127.0.0.1", ListenPort: ports[index]})
	}
	return testWorkspace
}

func allocateNodeTestPorts(count int, reserved uint16) ([]uint16, error) {
	ports := make([]uint16, 0, count)
	used := map[uint16]bool{reserved: true}
	for len(ports) < count {
		listener, err := net.Listen("tcp4", "127.0.0.1:0")
		if err != nil {
			return nil, fmt.Errorf("allocate local test listener: %w", err)
		}
		port := uint16(listener.Addr().(*net.TCPAddr).Port)
		_ = listener.Close()
		if used[port] {
			continue
		}
		used[port] = true
		ports = append(ports, port)
	}
	return ports, nil
}

func waitForNodeTestListeners(ctx context.Context, ports []uint16, processWait <-chan error) error {
	ready := make([]bool, len(ports))
	remaining := len(ports)
	deadline := time.Now().Add(8 * time.Second)
	for remaining > 0 && time.Now().Before(deadline) {
		if err := ctx.Err(); err != nil {
			return err
		}
		select {
		case processErr := <-processWait:
			return fmt.Errorf("temporary core exited before listeners were ready: %w", processErr)
		default:
		}
		for index, port := range ports {
			if ready[index] {
				continue
			}
			connection, err := net.DialTimeout("tcp", net.JoinHostPort("127.0.0.1", strconv.Itoa(int(port))), 100*time.Millisecond)
			if err == nil {
				_ = connection.Close()
				ready[index] = true
				remaining--
			}
		}
		if remaining > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(75 * time.Millisecond):
			}
		}
	}
	if remaining > 0 {
		return fmt.Errorf("temporary core did not open %d of %d mixed listeners", remaining, len(ports))
	}
	return nil
}

func nodeTestURL(configured string) (string, error) {
	value := strings.TrimSpace(configured)
	if value == "" {
		value = defaultNodeTestURL
	}
	parsed, err := url.ParseRequestURI(value)
	if err != nil || parsed.Host == "" || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		return "", fmt.Errorf("Real Delay URL must be a valid HTTP or HTTPS URL")
	}
	return value, nil
}

func measureV2RayRealDelay(parent context.Context, proxyPort uint16, testURL string) (time.Duration, error) {
	var lastErr error
	for retry := 0; retry < 2; retry++ {
		delay, err := measureV2RayRealDelayRound(parent, proxyPort, testURL)
		if err == nil && delay > 0 {
			return delay, nil
		}
		lastErr = err
		if retry == 0 {
			select {
			case <-parent.Done():
				return 0, parent.Err()
			case <-time.After(500 * time.Millisecond):
			}
		}
	}
	if lastErr == nil {
		lastErr = errors.New("real delay returned no positive response time")
	}
	return 0, fmt.Errorf("real delay failed after two attempts: %w", lastErr)
}

func measureV2RayRealDelayRound(parent context.Context, proxyPort uint16, testURL string) (time.Duration, error) {
	ctx, cancel := context.WithTimeout(parent, nodeTestRealDelayTimeout)
	defer cancel()
	proxyAddress := net.JoinHostPort("127.0.0.1", strconv.Itoa(int(proxyPort)))
	transport := &http.Transport{
		DialContext: func(dialCtx context.Context, network, address string) (net.Conn, error) {
			return dialSOCKS5Context(dialCtx, proxyAddress, address)
		},
		TLSHandshakeTimeout:   nodeTestRealDelayTimeout,
		ResponseHeaderTimeout: nodeTestRealDelayTimeout,
	}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport}
	delays := make([]time.Duration, 0, 2)
	for attempt := 0; attempt < 2; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, testURL, nil)
		if err != nil {
			return 0, err
		}
		started := time.Now()
		response, err := client.Do(request)
		if err != nil {
			return 0, fmt.Errorf("HTTP GET %d/2 through SOCKS5 failed: %w", attempt+1, err)
		}
		_, readErr := io.Copy(io.Discard, response.Body)
		_ = response.Body.Close()
		if readErr != nil {
			return 0, fmt.Errorf("read HTTP GET %d/2 response: %w", attempt+1, readErr)
		}
		delays = append(delays, time.Since(started))
		if attempt == 0 {
			select {
			case <-ctx.Done():
				return 0, ctx.Err()
			case <-time.After(100 * time.Millisecond):
			}
		}
	}
	if delays[1] < delays[0] {
		return delays[1], nil
	}
	return delays[0], nil
}

func dialSOCKS5Context(ctx context.Context, proxyAddress, targetAddress string) (net.Conn, error) {
	connection, err := (&net.Dialer{}).DialContext(ctx, "tcp", proxyAddress)
	if err != nil {
		return nil, fmt.Errorf("connect to local SOCKS5 listener: %w", err)
	}
	failed := true
	defer func() {
		if failed {
			_ = connection.Close()
		}
	}()
	if deadline, ok := ctx.Deadline(); ok {
		_ = connection.SetDeadline(deadline)
	}
	if _, err := connection.Write([]byte{0x05, 0x01, 0x00}); err != nil {
		return nil, fmt.Errorf("write SOCKS5 greeting: %w", err)
	}
	var greeting [2]byte
	if _, err := io.ReadFull(connection, greeting[:]); err != nil {
		return nil, fmt.Errorf("read SOCKS5 greeting: %w", err)
	}
	if greeting[0] != 0x05 || greeting[1] != 0x00 {
		return nil, fmt.Errorf("SOCKS5 listener rejected no-auth method: %v", greeting)
	}
	host, portText, err := net.SplitHostPort(targetAddress)
	if err != nil {
		return nil, fmt.Errorf("parse proxy destination %q: %w", targetAddress, err)
	}
	port, err := strconv.ParseUint(portText, 10, 16)
	if err != nil {
		return nil, fmt.Errorf("parse proxy destination port: %w", err)
	}
	ip := net.ParseIP(host)
	request := []byte{0x05, 0x01, 0x00}
	if ip4 := ip.To4(); ip4 != nil {
		request = append(request, 0x01)
		request = append(request, ip4...)
	} else if ip6 := ip.To16(); ip6 != nil {
		request = append(request, 0x04)
		request = append(request, ip6...)
	} else {
		if len(host) == 0 || len(host) > 255 {
			return nil, errors.New("SOCKS5 destination hostname length is invalid")
		}
		request = append(request, 0x03, byte(len(host)))
		request = append(request, host...)
	}
	request = append(request, byte(port>>8), byte(port))
	if _, err := connection.Write(request); err != nil {
		return nil, fmt.Errorf("write SOCKS5 connect request: %w", err)
	}
	var reply [4]byte
	if _, err := io.ReadFull(connection, reply[:]); err != nil {
		return nil, fmt.Errorf("read SOCKS5 connect reply: %w", err)
	}
	if reply[0] != 0x05 || reply[1] != 0x00 {
		return nil, fmt.Errorf("SOCKS5 connect failed with reply code %d", reply[1])
	}
	var addressLength int
	switch reply[3] {
	case 0x01:
		addressLength = 4
	case 0x04:
		addressLength = 16
	case 0x03:
		var size [1]byte
		if _, err := io.ReadFull(connection, size[:]); err != nil {
			return nil, fmt.Errorf("read SOCKS5 bound hostname: %w", err)
		}
		addressLength = int(size[0])
	default:
		return nil, fmt.Errorf("SOCKS5 returned unsupported address type %d", reply[3])
	}
	if _, err := io.CopyN(io.Discard, connection, int64(addressLength+2)); err != nil {
		return nil, fmt.Errorf("read SOCKS5 bound address: %w", err)
	}
	_ = connection.SetDeadline(time.Time{})
	failed = false
	return connection, nil
}
