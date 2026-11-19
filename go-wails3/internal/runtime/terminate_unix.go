//go:build !windows

package runtime

import (
	"os"
	"os/exec"
	"syscall"
)

func configureProcess(cmd *exec.Cmd)             { cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true} }
func terminateProcess(process *os.Process) error { return syscall.Kill(-process.Pid, syscall.SIGTERM) }
func killProcess(process *os.Process) error      { return syscall.Kill(-process.Pid, syscall.SIGKILL) }
