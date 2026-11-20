//go:build !windows

package service

import "os"

func replaceExportFile(source, destination string) error {
	return os.Rename(source, destination)
}
