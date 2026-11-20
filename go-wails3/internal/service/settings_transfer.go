package service

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
)

const settingsFileFormat = "chainport-settings"

type settingsFile struct {
	Format   string          `json:"format"`
	Version  int             `json:"version"`
	Settings domain.Settings `json:"settings"`
}

func (s *WorkspaceService) ExportSettings() error {
	s.mu.RLock()
	picker := s.selectSaveFile
	settings := s.state.Settings
	s.mu.RUnlock()
	if picker == nil {
		return errors.New("save-file dialog is unavailable")
	}
	path, err := picker("Export ChainPort Settings")
	if err != nil || path == "" {
		return err
	}
	if filepath.Ext(path) == "" {
		path += ".json"
	}
	// Executable paths and custom runtime output directories are machine-local.
	settings.Core.Executable = map[string]string{}
	settings.ConfigOutputDir = ""
	data, err := json.MarshalIndent(settingsFile{Format: settingsFileFormat, Version: 1, Settings: settings}, "", "  ")
	if err != nil {
		return err
	}
	return writePrivateFile(path, data)
}

func (s *WorkspaceService) ImportSettings() (domain.Workspace, error) {
	s.mu.RLock()
	picker := s.selectOpenFile
	s.mu.RUnlock()
	if picker == nil {
		return domain.Workspace{}, errors.New("open-file dialog is unavailable")
	}
	path, err := picker("Import ChainPort Settings")
	if err != nil {
		return domain.Workspace{}, err
	}
	if path == "" {
		return domain.Workspace{}, nil
	}
	file, err := os.Open(path)
	if err != nil {
		return domain.Workspace{}, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, 4*1024*1024+1))
	if err != nil {
		return domain.Workspace{}, err
	}
	if len(data) > 4*1024*1024 {
		return domain.Workspace{}, errors.New("settings file exceeds the 4 MiB import limit")
	}
	var input settingsFile
	if err := json.Unmarshal(data, &input); err != nil {
		return domain.Workspace{}, fmt.Errorf("decode settings file: %w", err)
	}
	if input.Format != settingsFileFormat || input.Version != 1 {
		return domain.Workspace{}, errors.New("unsupported ChainPort settings file format or version")
	}
	current := s.GetWorkspace().Settings
	input.Settings.Core.Executable = current.Core.Executable
	input.Settings.ConfigOutputDir = current.ConfigOutputDir
	return s.UpdateSettings(input.Settings)
}

func writePrivateFile(path string, data []byte) error {
	path, err := filepath.Abs(path)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".chainport-export-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath)
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return err
	}
	if _, err := tmp.Write(data); err != nil {
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
	if err := replaceExportFile(tmpPath, path); err != nil {
		return err
	}
	return nil
}
