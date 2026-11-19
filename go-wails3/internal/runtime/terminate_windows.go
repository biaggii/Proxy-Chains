//go:build windows

package runtime

import (
	"os"
	"os/exec"
)

func configureProcess(cmd *exec.Cmd)             {}
func terminateProcess(process *os.Process) error { return process.Kill() }
func killProcess(process *os.Process) error      { return process.Kill() }
