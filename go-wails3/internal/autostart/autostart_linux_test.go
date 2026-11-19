//go:build linux

package autostart

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSetEnabledWritesAndRemovesDesktopAutostart(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	if err := SetEnabled(true); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(home, ".config", "autostart", "chainport-gateway.desktop")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), "X-GNOME-Autostart-enabled=true") || !strings.Contains(string(data), "Exec=") {
		t.Fatalf("invalid desktop entry: %s", data)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("unexpected autostart file permissions: %o", info.Mode().Perm())
	}
	if err := SetEnabled(false); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("autostart desktop entry was not removed")
	}
}
