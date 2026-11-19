//go:build windows

package tun

import "golang.org/x/sys/windows"

func HasPrivileges() (bool, string) {
	if windows.GetCurrentProcessToken().IsElevated() {
		return true, ""
	}
	return false, "TUN requires an elevated Administrator session; restart ChainPort as Administrator"
}
