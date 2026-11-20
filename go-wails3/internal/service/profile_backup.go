package service

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/autostart"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
)

const profileBackupIterations = 600000

type encryptedProfileBackup struct {
	Format     string `json:"format"`
	Version    int    `json:"version"`
	KDF        string `json:"kdf"`
	Iterations int    `json:"iterations"`
	Salt       string `json:"salt"`
	Nonce      string `json:"nonce"`
	Ciphertext string `json:"ciphertext"`
}

type profileBackupPayload struct {
	Workspace domain.Workspace  `json:"workspace"`
	Secrets   map[string]string `json:"secrets"`
}

func (s *WorkspaceService) ExportProfileBackup(password string) (bool, error) {
	if len(password) < 12 {
		return false, errors.New("backup password must contain at least 12 characters")
	}
	s.mu.RLock()
	picker := s.selectSaveFile
	workspace := cloneWorkspace(s.state)
	secretStore := s.secrets
	ctx := s.appContext
	s.mu.RUnlock()
	if picker == nil {
		return false, errors.New("save-file dialog is unavailable")
	}
	if secretStore == nil || !secretStore.Available() {
		return false, errors.New("OS credential vault is unavailable; cannot create a complete profile backup")
	}
	workspace.Settings.Core.Executable = map[string]string{}
	workspace.Settings.ConfigOutputDir = ""
	path, err := picker("Export Encrypted ChainPort Profile Backup")
	if err != nil {
		return false, err
	}
	if path == "" {
		return false, nil
	}
	if !strings.HasSuffix(strings.ToLower(path), ".cpbackup") {
		path += ".cpbackup"
	}
	secrets := map[string]string{}
	for _, ref := range workspaceSecretReferences(workspace) {
		value, getErr := secretStore.Get(ctx, ref)
		if getErr != nil {
			return false, fmt.Errorf("read credential %q for backup: %w", ref, getErr)
		}
		secrets[ref] = value
	}
	payload, err := json.Marshal(profileBackupPayload{Workspace: workspace, Secrets: secrets})
	if err != nil {
		return false, err
	}
	data, err := encryptProfileBackup(payload, password)
	if err != nil {
		return false, err
	}
	if err := writePrivateFile(path, data); err != nil {
		return false, err
	}
	return true, nil
}

func (s *WorkspaceService) ImportProfileBackup(password string) (domain.Workspace, error) {
	if len(password) < 12 {
		return domain.Workspace{}, errors.New("backup password must contain at least 12 characters")
	}
	s.mu.RLock()
	picker := s.selectOpenFile
	s.mu.RUnlock()
	if picker == nil {
		return domain.Workspace{}, errors.New("open-file dialog is unavailable")
	}
	path, err := picker("Import Encrypted ChainPort Profile Backup")
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
	data, err := io.ReadAll(io.LimitReader(file, 64*1024*1024+1))
	if err != nil {
		return domain.Workspace{}, err
	}
	if len(data) > 64*1024*1024 {
		return domain.Workspace{}, errors.New("profile backup exceeds the 64 MiB import limit")
	}
	plain, err := decryptProfileBackup(data, password)
	if err != nil {
		return domain.Workspace{}, err
	}
	var payload profileBackupPayload
	if err := json.Unmarshal(plain, &payload); err != nil {
		return domain.Workspace{}, fmt.Errorf("decode profile backup: %w", err)
	}
	candidate := cloneWorkspace(payload.Workspace)
	current := s.GetWorkspace().Settings
	candidate.Settings.Core.Executable = current.Core.Executable
	candidate.Settings.ConfigOutputDir = current.ConfigOutputDir
	if err := candidate.Validate(); err != nil {
		return domain.Workspace{}, fmt.Errorf("backup workspace is invalid: %w", err)
	}
	for _, reference := range workspaceSecretReferences(candidate) {
		if _, ok := payload.Secrets[reference]; !ok {
			return domain.Workspace{}, fmt.Errorf("profile backup is missing credential %q", reference)
		}
	}
	s.mu.RLock()
	secretStore := s.secrets
	ctx := s.appContext
	s.mu.RUnlock()
	if secretStore == nil || !secretStore.Available() {
		return domain.Workspace{}, errors.New("OS credential vault is unavailable; cannot restore profile credentials")
	}
	remapped := map[string]string{}
	for _, oldRef := range workspaceSecretReferences(candidate) {
		value := payload.Secrets[oldRef]
		newRef, err := newID()
		if err != nil {
			cleanupBackupSecrets(ctx, secretStore, remapped)
			return domain.Workspace{}, err
		}
		newRef = "chainport:" + newRef
		remapped[oldRef] = newRef
		if err := secretStore.Put(ctx, newRef, value); err != nil {
			cleanupBackupSecrets(ctx, secretStore, remapped)
			return domain.Workspace{}, fmt.Errorf("restore credential to OS vault: %w", err)
		}
	}
	rewriteWorkspaceSecretReferences(&candidate, remapped)
	if err := candidate.Validate(); err != nil {
		cleanupBackupSecrets(ctx, secretStore, remapped)
		return domain.Workspace{}, err
	}
	if err := s.StopCore(); err != nil {
		cleanupBackupSecrets(ctx, secretStore, remapped)
		return domain.Workspace{}, fmt.Errorf("stop core before restoring profile: %w", err)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.refreshingSubscriptions) > 0 {
		cleanupBackupSecrets(ctx, secretStore, remapped)
		return domain.Workspace{}, errors.New("wait for subscription refreshes to finish before restoring a profile")
	}
	previousStartup := s.state.Settings.RunOnStartup
	if candidate.Settings.RunOnStartup != previousStartup {
		if err := autostart.SetEnabled(candidate.Settings.RunOnStartup); err != nil {
			cleanupBackupSecrets(ctx, secretStore, remapped)
			return domain.Workspace{}, fmt.Errorf("update system startup registration: %w", err)
		}
	}
	result, err := s.commit(candidate)
	if err != nil {
		if candidate.Settings.RunOnStartup != previousStartup {
			_ = autostart.SetEnabled(previousStartup)
		}
		cleanupBackupSecrets(ctx, secretStore, remapped)
		return domain.Workspace{}, err
	}
	return result, nil
}

func cleanupBackupSecrets(ctx context.Context, store interface {
	Delete(context.Context, string) error
}, refs map[string]string) {
	for _, ref := range refs {
		_ = store.Delete(ctx, ref)
	}
}

func workspaceSecretReferences(w domain.Workspace) []string {
	seen := map[string]bool{}
	result := []string{}
	add := func(ref string) {
		if ref != "" && !seen[ref] {
			seen[ref] = true
			result = append(result, ref)
		}
	}
	for _, node := range w.Nodes {
		add(node.Credentials.UsernameRef)
		add(node.Credentials.PasswordRef)
		add(node.Credentials.UUIDRef)
		add(node.Credentials.PrivateKeyRef)
		add(node.SourceMetadataRef)
	}
	for _, sub := range w.Subscriptions {
		add(sub.URLSecretRef)
		add(sub.LegacyMetadataRef)
		for _, ref := range sub.HeaderSecretRefs {
			add(ref)
		}
	}
	return result
}

func rewriteWorkspaceSecretReferences(w *domain.Workspace, refs map[string]string) {
	lookup := func(ref string) string {
		if value, ok := refs[ref]; ok {
			return value
		}
		return ref
	}
	for i := range w.Nodes {
		w.Nodes[i].Credentials.UsernameRef = lookup(w.Nodes[i].Credentials.UsernameRef)
		w.Nodes[i].Credentials.PasswordRef = lookup(w.Nodes[i].Credentials.PasswordRef)
		w.Nodes[i].Credentials.UUIDRef = lookup(w.Nodes[i].Credentials.UUIDRef)
		w.Nodes[i].Credentials.PrivateKeyRef = lookup(w.Nodes[i].Credentials.PrivateKeyRef)
		w.Nodes[i].SourceMetadataRef = lookup(w.Nodes[i].SourceMetadataRef)
	}
	for i := range w.Subscriptions {
		w.Subscriptions[i].URLSecretRef = lookup(w.Subscriptions[i].URLSecretRef)
		w.Subscriptions[i].LegacyMetadataRef = lookup(w.Subscriptions[i].LegacyMetadataRef)
		for key, ref := range w.Subscriptions[i].HeaderSecretRefs {
			w.Subscriptions[i].HeaderSecretRefs[key] = lookup(ref)
		}
	}
}

func encryptProfileBackup(plain []byte, password string) ([]byte, error) {
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return nil, err
	}
	key := pbkdf2SHA256([]byte(password), salt, profileBackupIterations, 32)
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}
	sealed := gcm.Seal(nil, nonce, plain, []byte("chainport-profile-backup:v1"))
	envelope := encryptedProfileBackup{Format: "chainport-profile-backup", Version: 1, KDF: "PBKDF2-HMAC-SHA256", Iterations: profileBackupIterations, Salt: base64.RawStdEncoding.EncodeToString(salt), Nonce: base64.RawStdEncoding.EncodeToString(nonce), Ciphertext: base64.RawStdEncoding.EncodeToString(sealed)}
	return json.MarshalIndent(envelope, "", "  ")
}

func decryptProfileBackup(data []byte, password string) ([]byte, error) {
	var envelope encryptedProfileBackup
	if err := json.Unmarshal(data, &envelope); err != nil {
		return nil, fmt.Errorf("decode encrypted profile backup: %w", err)
	}
	if envelope.Format != "chainport-profile-backup" || envelope.Version != 1 || envelope.KDF != "PBKDF2-HMAC-SHA256" || envelope.Iterations < 300000 || envelope.Iterations > 2000000 {
		return nil, errors.New("unsupported or unsafe profile backup format")
	}
	salt, err := base64.RawStdEncoding.DecodeString(envelope.Salt)
	if err != nil || len(salt) != 16 {
		return nil, errors.New("invalid profile backup salt")
	}
	nonce, err := base64.RawStdEncoding.DecodeString(envelope.Nonce)
	if err != nil {
		return nil, errors.New("invalid profile backup nonce")
	}
	sealed, err := base64.RawStdEncoding.DecodeString(envelope.Ciphertext)
	if err != nil {
		return nil, errors.New("invalid profile backup ciphertext")
	}
	key := pbkdf2SHA256([]byte(password), salt, envelope.Iterations, 32)
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	if len(nonce) != gcm.NonceSize() {
		return nil, errors.New("invalid profile backup nonce size")
	}
	plain, err := gcm.Open(nil, nonce, sealed, []byte("chainport-profile-backup:v1"))
	if err != nil {
		return nil, errors.New("profile backup password is incorrect or the file has been modified")
	}
	return plain, nil
}

func pbkdf2SHA256(password, salt []byte, iterations, keyLength int) []byte {
	hashLength := sha256.Size
	blocks := (keyLength + hashLength - 1) / hashLength
	derived := make([]byte, 0, blocks*hashLength)
	for block := 1; block <= blocks; block++ {
		mac := hmac.New(sha256.New, password)
		_, _ = mac.Write(salt)
		_, _ = mac.Write([]byte{byte(block >> 24), byte(block >> 16), byte(block >> 8), byte(block)})
		u := mac.Sum(nil)
		t := append([]byte(nil), u...)
		for i := 1; i < iterations; i++ {
			mac = hmac.New(sha256.New, password)
			_, _ = mac.Write(u)
			u = mac.Sum(nil)
			for j := range t {
				t[j] ^= u[j]
			}
		}
		derived = append(derived, t...)
	}
	return derived[:keyLength]
}
