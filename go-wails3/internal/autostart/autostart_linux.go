//go:build linux

package autostart

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func SetEnabled(enabled bool) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	path := filepath.Join(home, ".config", "autostart", "chainport-gateway.desktop")
	if !enabled {
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			return err
		}
		return nil
	}
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	executable, err = filepath.Abs(executable)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	content := fmt.Sprintf("[Desktop Entry]\nType=Application\nName=ChainPort Gateway\nComment=Proxy chain manager\nExec=%s\nTerminal=false\nX-GNOME-Autostart-enabled=true\n", desktopEscape(executable))
	return os.WriteFile(path, []byte(content), 0o600)
}

func desktopEscape(value string) string {
	value = strings.ReplaceAll(value, "\\", "\\\\")
	value = strings.ReplaceAll(value, " ", "\\s")
	value = strings.ReplaceAll(value, "\"", "\\\"")
	return value
}
