//go:build !linux && !windows

package tun

import "os"

func HasPrivileges() (bool, string) {
	if os.Geteuid() == 0 {
		return true, ""
	}
	return false, "TUN requires administrator/root privileges; restart ChainPort with elevated permissions"
}
