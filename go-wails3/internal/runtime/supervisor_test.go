package runtime

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestSupervisorStartStopAndRedactLogs(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell process fixture is Unix-only")
	}
	events := make(chan Event, 16)
	s := NewSupervisor(func(event Event) { events <- event })
	if err := s.Start(context.Background(), []string{"/bin/sh", "-c", "echo password-secret; sleep 10"}, []string{"password-secret"}); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for s.Snapshot().Status != StatusRunning && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if s.Snapshot().Status != StatusRunning {
		t.Fatalf("core not running: %+v", s.Snapshot())
	}
	deadline = time.Now().Add(2 * time.Second)
	for len(s.Logs()) == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if strings.Contains(strings.Join(s.Logs(), "\n"), "password-secret") {
		t.Fatal("secret leaked into runtime logs")
	}
	if err := s.Stop(); err != nil {
		t.Fatal(err)
	}
	deadline = time.Now().Add(2 * time.Second)
	for s.Snapshot().Status == StatusStopping && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if s.Snapshot().Status != StatusStopped && s.Snapshot().Status != StatusFailed {
		t.Fatalf("unexpected stopped state: %+v", s.Snapshot())
	}
}

func TestWriteConfigUsesPrivatePermissionsAndAtomicReplace(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "configs")
	path, err := WriteConfig(dir, "core.json", []byte(`{"secret":"value"}`))
	if err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("config permissions are %o", info.Mode().Perm())
	}
	if _, err := WriteConfig(dir, "../escape.json", []byte("x")); err != nil {
		t.Fatal(err)
	}
	if filepath.Dir(path) != dir {
		t.Fatal("config path escaped target directory")
	}
	if _, err := WriteConfig(dir, "core.json", []byte(`{"updated":true}`)); err != nil {
		t.Fatalf("atomic replacement failed: %v", err)
	}
	updated, err := os.ReadFile(path)
	if err != nil || string(updated) != `{"updated":true}` {
		t.Fatalf("config was not replaced: %s / %v", updated, err)
	}
}

func TestRunCheckRedactsSecretsFromValidationOutput(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell validation fixture is Unix-only")
	}
	s := NewSupervisor(nil)
	output, err := s.RunCheck(context.Background(), []string{"/bin/sh", "-c", "printf 'token-secret'"}, []string{"token-secret"})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(output, "token-secret") || !strings.Contains(output, "[REDACTED]") {
		t.Fatalf("validation output was not redacted: %q", output)
	}
}

func TestAppendLogStoresAndEmitsRedactedApplicationDiagnostics(t *testing.T) {
	events := make(chan Event, 1)
	supervisor := NewSupervisor(func(event Event) { events <- event })
	supervisor.mu.Lock()
	supervisor.redactions = []string{"sensitive-token"}
	supervisor.mu.Unlock()
	supervisor.AppendLog("startup failed: sensitive-token")
	logs := supervisor.Logs()
	if len(logs) != 1 || strings.Contains(logs[0], "sensitive-token") || !strings.Contains(logs[0], "[REDACTED]") {
		t.Fatalf("application log was not stored/redacted: %+v", logs)
	}
	select {
	case event := <-events:
		if event.Type != "log" || strings.Contains(event.Message, "sensitive-token") {
			t.Fatalf("unexpected log event: %+v", event)
		}
	case <-time.After(time.Second):
		t.Fatal("application log event was not emitted")
	}
}
