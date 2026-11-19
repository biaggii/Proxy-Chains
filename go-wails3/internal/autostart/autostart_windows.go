//go:build windows

package autostart

import (
	"os"
	"strings"

	"golang.org/x/sys/windows/registry"
)

func SetEnabled(enabled bool) error {
	key, _, err := registry.CreateKey(registry.CURRENT_USER, `Software\Microsoft\Windows\CurrentVersion\Run`, registry.SET_VALUE|registry.QUERY_VALUE)
	if err != nil {
		return err
	}
	defer key.Close()
	if !enabled {
		err := key.DeleteValue("ChainPort Gateway")
		if err == registry.ErrNotExist {
			return nil
		}
		return err
	}
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	executable = strings.ReplaceAll(executable, `"`, `\"`)
	return key.SetStringValue("ChainPort Gateway", `"`+executable+`" --autostart`)
}
