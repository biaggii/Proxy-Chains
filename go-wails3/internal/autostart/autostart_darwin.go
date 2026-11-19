//go:build darwin

package autostart

import (
	"bytes"
	"encoding/xml"
	"os"
	"path/filepath"
)

func SetEnabled(enabled bool) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	path := filepath.Join(home, "Library", "LaunchAgents", "com.chainport.gateway.plist")
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
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	content := []byte(xml.Header + "<plist version=\"1.0\"><dict><key>Label</key><string>com.chainport.gateway</string><key>ProgramArguments</key><array><string>" + xmlEscape(executable) + "</string><string>--autostart</string></array><key>RunAtLoad</key><true/><key>KeepAlive</key><false/></dict></plist>\n")
	tmp, err := os.CreateTemp(filepath.Dir(path), ".chainport-launchagent-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath)
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return err
	}
	if _, err := tmp.Write(content); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpPath, path)
}

func xmlEscape(value string) string {
	var buffer bytes.Buffer
	_ = xml.EscapeText(&buffer, []byte(value))
	return buffer.String()
}
