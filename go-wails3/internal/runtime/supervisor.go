package runtime

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type Status string

const (
	StatusStopped  Status = "stopped"
	StatusStarting Status = "starting"
	StatusRunning  Status = "running"
	StatusStopping Status = "stopping"
	StatusFailed   Status = "failed"
)

type Snapshot struct {
	Status    Status    `json:"status"`
	PID       int       `json:"pid,omitempty"`
	StartedAt time.Time `json:"startedAt,omitempty"`
	ExitCode  int       `json:"exitCode,omitempty"`
	LastError string    `json:"lastError,omitempty"`
}
type Event struct {
	Type     string   `json:"type"`
	Message  string   `json:"message,omitempty"`
	Snapshot Snapshot `json:"snapshot"`
}

type Supervisor struct {
	mu         sync.RWMutex
	cmd        *exec.Cmd
	cancel     context.CancelFunc
	waitDone   chan struct{}
	stopping   bool
	snapshot   Snapshot
	logs       []string
	redactions []string
	onEvent    func(Event)
	maxLogs    int
}

func NewSupervisor(onEvent func(Event)) *Supervisor {
	return &Supervisor{snapshot: Snapshot{Status: StatusStopped}, onEvent: onEvent, maxLogs: 2000}
}

func (s *Supervisor) Snapshot() Snapshot { s.mu.RLock(); defer s.mu.RUnlock(); return s.snapshot }
func (s *Supervisor) Logs() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return append([]string(nil), s.logs...)
}

func (s *Supervisor) ClearLogs() { s.mu.Lock(); s.logs = nil; s.mu.Unlock() }

// AppendLog records application and preflight diagnostics in the same bounded,
// redacted log buffer used for the child process streams.
func (s *Supervisor) AppendLog(message string) {
	line := s.redact(message)
	s.mu.Lock()
	s.logs = append(s.logs, "[chainport] "+line)
	if len(s.logs) > s.maxLogs {
		s.logs = append([]string(nil), s.logs[len(s.logs)-s.maxLogs:]...)
	}
	s.mu.Unlock()
	s.emit(Event{Type: "log", Message: line, Snapshot: s.Snapshot()})
}

func (s *Supervisor) Start(parent context.Context, command []string, secrets []string) error {
	if len(command) == 0 || strings.TrimSpace(command[0]) == "" {
		return errors.New("core start command is empty")
	}
	s.mu.Lock()
	if s.cmd != nil {
		s.mu.Unlock()
		return errors.New("a core process is already running")
	}
	ctx, cancel := context.WithCancel(parent)
	cmd := exec.CommandContext(ctx, command[0], command[1:]...)
	configureProcess(cmd)
	cmd.Cancel = func() error {
		if cmd.Process == nil {
			return os.ErrProcessDone
		}
		return terminateProcess(cmd.Process)
	}
	cmd.WaitDelay = 2 * time.Second
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		cancel()
		s.mu.Unlock()
		return fmt.Errorf("open core stdout: %w", err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		cancel()
		s.mu.Unlock()
		return fmt.Errorf("open core stderr: %w", err)
	}
	s.snapshot = Snapshot{Status: StatusStarting}
	done := make(chan struct{})
	s.cmd, s.cancel, s.redactions, s.waitDone, s.stopping = cmd, cancel, cleanSecrets(secrets), done, false
	if err := cmd.Start(); err != nil {
		s.cmd = nil
		s.cancel = nil
		s.waitDone = nil
		s.snapshot = Snapshot{Status: StatusFailed, ExitCode: -1, LastError: err.Error()}
		s.mu.Unlock()
		cancel()
		s.emit(Event{Type: "status", Snapshot: s.Snapshot()})
		return fmt.Errorf("start core: %w", err)
	}
	s.snapshot = Snapshot{Status: StatusRunning, PID: cmd.Process.Pid, StartedAt: time.Now()}
	s.mu.Unlock()
	s.emit(Event{Type: "status", Snapshot: s.Snapshot()})
	go s.readLogs("stdout", stdout)
	go s.readLogs("stderr", stderr)
	go func() {
		defer close(done)
		err := cmd.Wait()
		cancel()
		s.mu.Lock()
		code := 0
		if err != nil {
			code = -1
			var exitErr *exec.ExitError
			if errors.As(err, &exitErr) {
				code = exitErr.ExitCode()
			}
		}
		if s.cmd == cmd {
			s.cmd = nil
			s.cancel = nil
			status := StatusStopped
			if err != nil && code != 0 && !s.stopping {
				status = StatusFailed
			}
			if s.stopping {
				code = 0
			}
			s.snapshot = Snapshot{Status: status, ExitCode: code}
			if err != nil && code != 0 && !s.stopping {
				s.snapshot.LastError = err.Error()
			}
			s.stopping = false
		}
		snapshot := s.snapshot
		s.mu.Unlock()
		s.emit(Event{Type: "status", Snapshot: snapshot})
	}()
	return nil
}

func (s *Supervisor) Stop() error {
	s.mu.Lock()
	cmd, cancel := s.cmd, s.cancel
	if cmd == nil {
		s.mu.Unlock()
		return nil
	}
	s.snapshot.Status = StatusStopping
	s.stopping = true
	done := s.waitDone
	s.mu.Unlock()
	s.emit(Event{Type: "status", Snapshot: s.Snapshot()})
	if cancel != nil {
		cancel()
	}
	if done != nil {
		select {
		case <-done:
			return nil
		case <-time.After(5 * time.Second):
		}
	}
	if cmd.Process != nil {
		_ = killProcess(cmd.Process)
	}
	if done != nil {
		<-done
	}
	return nil
}

func (s *Supervisor) RunCheck(ctx context.Context, command []string, secrets []string) (string, error) {
	if len(command) == 0 {
		return "", errors.New("core validation command is empty")
	}
	s.mu.Lock()
	s.redactions = cleanSecrets(secrets)
	s.mu.Unlock()
	checkCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	cmd := exec.CommandContext(checkCtx, command[0], command[1:]...)
	output, err := cmd.CombinedOutput()
	clean := s.redact(string(output))
	if err != nil {
		return clean, fmt.Errorf("core configuration validation failed: %w", err)
	}
	return clean, nil
}

func WriteConfig(directory, filename string, data []byte) (string, error) {
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return "", fmt.Errorf("create core config directory: %w", err)
	}
	if err := os.Chmod(directory, 0o700); err != nil {
		return "", fmt.Errorf("restrict core config directory permissions: %w", err)
	}
	path := filepath.Join(directory, filepath.Base(filename))
	tmp, err := os.CreateTemp(directory, ".chainport-config-*")
	if err != nil {
		return "", err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return "", err
	}
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return "", err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return "", err
	}
	if err := tmp.Close(); err != nil {
		return "", err
	}
	if err := replaceFile(tmpName, path); err != nil {
		return "", fmt.Errorf("replace core config: %w", err)
	}
	if err := os.Chmod(path, 0o600); err != nil {
		return "", err
	}
	return path, nil
}

func (s *Supervisor) readLogs(stream string, reader io.Reader) {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	for scanner.Scan() {
		line := s.redact(scanner.Text())
		s.mu.Lock()
		s.logs = append(s.logs, "["+stream+"] "+line)
		if len(s.logs) > s.maxLogs {
			s.logs = append([]string(nil), s.logs[len(s.logs)-s.maxLogs:]...)
		}
		s.mu.Unlock()
		s.emit(Event{Type: "log", Message: line, Snapshot: s.Snapshot()})
	}
	if err := scanner.Err(); err != nil {
		s.mu.Lock()
		s.logs = append(s.logs, "[supervisor] log stream error: "+err.Error())
		s.mu.Unlock()
	}
}

func (s *Supervisor) redact(value string) string {
	s.mu.RLock()
	secrets := append([]string(nil), s.redactions...)
	s.mu.RUnlock()
	for _, secret := range secrets {
		if secret != "" {
			value = strings.ReplaceAll(value, secret, "[REDACTED]")
		}
	}
	return value
}
func (s *Supervisor) emit(event Event) {
	if s.onEvent != nil {
		s.onEvent(event)
	}
}
func cleanSecrets(values []string) []string {
	result := []string{}
	seen := map[string]bool{}
	for _, value := range values {
		if value != "" && !seen[value] {
			seen[value] = true
			result = append(result, value)
		}
	}
	return result
}
