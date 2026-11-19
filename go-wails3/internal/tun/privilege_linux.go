//go:build linux

package tun

import (
	"bufio"
	"os"
	"strconv"
	"strings"
)

// HasPrivileges checks CAP_NET_ADMIN rather than assuming UID 0 implies that
// the process can configure routes inside a container or restricted namespace.
func HasPrivileges() (bool, string) {
	file, err := os.Open("/proc/self/status")
	if err != nil {
		return false, "cannot inspect Linux capabilities; run with CAP_NET_ADMIN"
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "CapEff:") {
			parts := strings.Fields(line)
			if len(parts) < 2 {
				return false, "cannot parse effective Linux capabilities"
			}
			value, err := strconv.ParseUint(parts[1], 16, 64)
			if err != nil {
				return false, "cannot parse effective Linux capabilities"
			}
			if value&(1<<12) != 0 {
				device, openErr := os.OpenFile("/dev/net/tun", os.O_RDWR, 0)
				if openErr != nil {
					return false, "/dev/net/tun is unavailable or inaccessible; enable the TUN device and CAP_NET_ADMIN"
				}
				_ = device.Close()
				return true, ""
			}
			return false, "Linux TUN requires CAP_NET_ADMIN (or root with that capability)"
		}
	}
	return false, "Linux effective capabilities are unavailable"
}
