package profiles

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/store"
)

type Profile struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	CreatedAt string `json:"createdAt"`
}

type State struct {
	Profiles        []Profile `json:"profiles"`
	ActiveProfileID string    `json:"activeProfileId"`
	DataLocation    string    `json:"dataLocation"`
}

type manifest struct {
	Version         int       `json:"version"`
	ActiveProfileID string    `json:"activeProfileId"`
	Profiles        []Profile `json:"profiles"`
}

// Manager is a WorkspaceStore whose active SQLite database can be switched
// without changing the service's persistence interface.
type Manager struct {
	mu       sync.Mutex
	root     string
	pointer  string
	manifest manifest
	active   *store.SQLiteStore
}

func Open(defaultRoot, pointerPath string) (*Manager, error) {
	defaultRoot, err := filepath.Abs(defaultRoot)
	if err != nil {
		return nil, err
	}
	root := defaultRoot
	if data, readErr := os.ReadFile(pointerPath); readErr == nil {
		var location struct {
			Root string `json:"root"`
		}
		if err := json.Unmarshal(data, &location); err != nil {
			return nil, fmt.Errorf("decode data location: %w", err)
		}
		if strings.TrimSpace(location.Root) != "" {
			root, err = filepath.Abs(location.Root)
			if err != nil {
				return nil, err
			}
		}
	} else if !os.IsNotExist(readErr) {
		return nil, readErr
	}
	if err := os.MkdirAll(root, 0o700); err != nil {
		return nil, fmt.Errorf("create profile data directory: %w", err)
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		return nil, fmt.Errorf("resolve profile data directory: %w", err)
	}
	pointerPath, err = filepath.Abs(pointerPath)
	if err != nil {
		return nil, err
	}
	m := &Manager{root: root, pointer: pointerPath}
	if err := m.loadManifest(); err != nil {
		return nil, err
	}
	if err := m.openActive(context.Background()); err != nil {
		return nil, err
	}
	return m, nil
}

func (m *Manager) loadManifest() error {
	path := filepath.Join(m.root, "profiles.json")
	data, err := os.ReadFile(path)
	if err == nil {
		if err := json.Unmarshal(data, &m.manifest); err != nil {
			return fmt.Errorf("decode profile index: %w", err)
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	if len(m.manifest.Profiles) == 0 {
		m.manifest = manifest{Version: 1, ActiveProfileID: "default", Profiles: []Profile{{ID: "default", Name: "Default", CreatedAt: time.Now().UTC().Format(time.RFC3339)}}}
		if err := m.saveManifest(); err != nil {
			return err
		}
	}
	if err := validateManifest(m.manifest); err != nil {
		return fmt.Errorf("validate profile index: %w", err)
	}
	return m.saveManifest()
}

func validateManifest(value manifest) error {
	if value.Version != 1 {
		return fmt.Errorf("unsupported profile index version %d", value.Version)
	}
	ids := map[string]bool{}
	names := map[string]bool{}
	for _, profile := range value.Profiles {
		if profile.ID != "default" {
			if len(profile.ID) != 32 {
				return fmt.Errorf("invalid profile ID %q", profile.ID)
			}
			if _, err := hex.DecodeString(profile.ID); err != nil {
				return fmt.Errorf("invalid profile ID %q", profile.ID)
			}
		}
		name := strings.ToLower(strings.TrimSpace(profile.Name))
		if name == "" || len(name) > 128 {
			return fmt.Errorf("invalid profile name for ID %q", profile.ID)
		}
		if ids[profile.ID] || names[name] {
			return fmt.Errorf("duplicate profile ID or name %q", profile.Name)
		}
		ids[profile.ID] = true
		names[name] = true
	}
	if !ids[value.ActiveProfileID] {
		return fmt.Errorf("active profile %q is not present in the profile index", value.ActiveProfileID)
	}
	return nil
}

func (m *Manager) profileDB(id string) string {
	if id == "default" {
		return filepath.Join(m.root, "chainport.db")
	}
	return filepath.Join(m.root, "profiles", id, "chainport.db")
}

func (m *Manager) openActive(ctx context.Context) error {
	db, err := store.OpenSQLite(m.profileDB(m.manifest.ActiveProfileID))
	if err != nil {
		return err
	}
	w, err := db.Load(ctx)
	if err == nil {
		err = w.Validate()
	}
	if err != nil {
		_ = db.Close()
		return fmt.Errorf("load profile %q: %w", m.manifest.ActiveProfileID, err)
	}
	m.active = db
	return nil
}

func (m *Manager) Load(ctx context.Context) (domain.Workspace, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.active == nil {
		return domain.Workspace{}, errors.New("profile database is closed")
	}
	return m.active.Load(ctx)
}

func (m *Manager) Save(ctx context.Context, workspace domain.Workspace) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.active == nil {
		return errors.New("profile database is closed")
	}
	return m.active.Save(ctx, workspace)
}

func (m *Manager) State() State {
	m.mu.Lock()
	defer m.mu.Unlock()
	return State{Profiles: append([]Profile(nil), m.manifest.Profiles...), ActiveProfileID: m.manifest.ActiveProfileID, DataLocation: m.root}
}

func (m *Manager) LoadProfile(id string) (domain.Workspace, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if !m.hasProfile(id) {
		return domain.Workspace{}, fmt.Errorf("profile %q does not exist", id)
	}
	if id == m.manifest.ActiveProfileID {
		return m.active.Load(context.Background())
	}
	db, err := store.OpenSQLite(m.profileDB(id))
	if err != nil {
		return domain.Workspace{}, err
	}
	defer db.Close()
	w, err := db.Load(context.Background())
	if err == nil {
		err = w.Validate()
	}
	return w, err
}

func (m *Manager) Create(name string) (Profile, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	name = strings.TrimSpace(name)
	if name == "" {
		return Profile{}, errors.New("profile name is required")
	}
	for _, item := range m.manifest.Profiles {
		if strings.EqualFold(item.Name, name) {
			return Profile{}, fmt.Errorf("profile %q already exists", name)
		}
	}
	id, err := randomID()
	if err != nil {
		return Profile{}, err
	}
	profile := Profile{ID: id, Name: name, CreatedAt: time.Now().UTC().Format(time.RFC3339)}
	db, err := store.OpenSQLite(m.profileDB(id))
	if err != nil {
		return Profile{}, err
	}
	if err := db.Save(context.Background(), domain.DefaultWorkspace()); err != nil {
		_ = db.Close()
		_ = os.RemoveAll(filepath.Dir(m.profileDB(id)))
		return Profile{}, err
	}
	if err := db.Close(); err != nil {
		return Profile{}, err
	}
	m.manifest.Profiles = append(m.manifest.Profiles, profile)
	if err := m.saveManifest(); err != nil {
		m.manifest.Profiles = m.manifest.Profiles[:len(m.manifest.Profiles)-1]
		_ = os.RemoveAll(filepath.Dir(m.profileDB(id)))
		return Profile{}, err
	}
	return profile, nil
}

func (m *Manager) Rename(id, name string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	name = strings.TrimSpace(name)
	if name == "" {
		return errors.New("profile name is required")
	}
	for _, p := range m.manifest.Profiles {
		if p.ID != id && strings.EqualFold(p.Name, name) {
			return fmt.Errorf("profile %q already exists", name)
		}
	}
	for i := range m.manifest.Profiles {
		if m.manifest.Profiles[i].ID == id {
			old := m.manifest.Profiles[i].Name
			m.manifest.Profiles[i].Name = name
			if err := m.saveManifest(); err != nil {
				m.manifest.Profiles[i].Name = old
				return err
			}
			return nil
		}
	}
	return fmt.Errorf("profile %q does not exist", id)
}

func (m *Manager) Delete(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if id == "default" {
		return errors.New("the Default profile cannot be deleted")
	}
	if id == m.manifest.ActiveProfileID {
		return errors.New("switch to another profile before deleting this one")
	}
	index := -1
	for i, p := range m.manifest.Profiles {
		if p.ID == id {
			index = i
			break
		}
	}
	if index < 0 {
		return fmt.Errorf("profile %q does not exist", id)
	}
	old := m.manifest.Profiles
	m.manifest.Profiles = append(m.manifest.Profiles[:index], m.manifest.Profiles[index+1:]...)
	if err := m.saveManifest(); err != nil {
		m.manifest.Profiles = old
		return err
	}
	return os.RemoveAll(filepath.Dir(m.profileDB(id)))
}

func (m *Manager) Switch(id string) (domain.Workspace, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if id == m.manifest.ActiveProfileID {
		return m.active.Load(context.Background())
	}
	if !m.hasProfile(id) {
		return domain.Workspace{}, fmt.Errorf("profile %q does not exist", id)
	}
	next, err := store.OpenSQLite(m.profileDB(id))
	if err != nil {
		return domain.Workspace{}, err
	}
	w, err := next.Load(context.Background())
	if err == nil {
		err = w.Validate()
	}
	if err != nil {
		_ = next.Close()
		return domain.Workspace{}, err
	}
	previousID := m.manifest.ActiveProfileID
	previous := m.active
	if previous != nil {
		if err := previous.Close(); err != nil {
			_ = next.Close()
			return domain.Workspace{}, fmt.Errorf("close previous profile database: %w", err)
		}
	}
	m.manifest.ActiveProfileID = id
	if err := m.saveManifest(); err != nil {
		m.manifest.ActiveProfileID = previousID
		_ = next.Close()
		reopened, reopenErr := store.OpenSQLite(m.profileDB(previousID))
		if reopenErr == nil {
			m.active = reopened
		} else {
			m.active = nil
			return domain.Workspace{}, errors.Join(err, fmt.Errorf("reopen previous profile database: %w", reopenErr))
		}
		return domain.Workspace{}, err
	}
	m.active = next
	return w, nil
}

func (m *Manager) MoveDataLocation(destination string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	destination = strings.TrimSpace(destination)
	if destination == "" {
		return errors.New("data location is required")
	}
	destination, err := filepath.Abs(destination)
	if err != nil {
		return err
	}
	if info, statErr := os.Lstat(destination); statErr == nil && info.Mode()&os.ModeSymlink != 0 {
		return errors.New("data location cannot be a symbolic link")
	} else if statErr != nil && !os.IsNotExist(statErr) {
		return statErr
	}
	if err := os.MkdirAll(filepath.Dir(destination), 0o700); err != nil {
		return err
	}
	resolvedParent, err := filepath.EvalSymlinks(filepath.Dir(destination))
	if err != nil {
		return err
	}
	destination = filepath.Join(resolvedParent, filepath.Base(destination))
	if samePath(destination, m.root) {
		return nil
	}
	if pathWithin(m.root, destination) || pathWithin(destination, m.root) {
		return errors.New("new data location cannot be inside or contain the current data location")
	}
	if info, err := os.Stat(destination); err == nil {
		if !info.IsDir() {
			return errors.New("data location must be a directory")
		}
		entries, readErr := os.ReadDir(destination)
		if readErr != nil {
			return readErr
		}
		if len(entries) > 0 {
			return errors.New("data location must be empty")
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	if m.active != nil {
		if err := m.active.Close(); err != nil {
			return err
		}
		m.active = nil
	}
	rollback := func() { _ = os.RemoveAll(destination); _ = m.openActive(context.Background()) }
	if err := copyDirectory(m.root, destination); err != nil {
		rollback()
		return fmt.Errorf("copy profile data: %w", err)
	}
	if err := validateCopiedProfiles(destination, m.manifest); err != nil {
		rollback()
		return fmt.Errorf("verify copied profile data: %w", err)
	}
	oldRoot := m.root
	m.root = destination
	next, err := store.OpenSQLite(m.profileDB(m.manifest.ActiveProfileID))
	if err != nil {
		m.root = oldRoot
		rollback()
		return err
	}
	if err := writeLocation(m.pointer, destination); err != nil {
		_ = next.Close()
		m.root = oldRoot
		rollback()
		return err
	}
	m.active = next
	return nil
}

func validateCopiedProfiles(root string, expected manifest) error {
	data, err := os.ReadFile(filepath.Join(root, "profiles.json"))
	if err != nil {
		return err
	}
	var copied manifest
	if err := json.Unmarshal(data, &copied); err != nil {
		return err
	}
	if copied.ActiveProfileID != expected.ActiveProfileID || len(copied.Profiles) != len(expected.Profiles) {
		return errors.New("copied profile index does not match the active profile index")
	}
	for _, profile := range expected.Profiles {
		found := false
		for _, candidate := range copied.Profiles {
			if candidate.ID == profile.ID && candidate.Name == profile.Name {
				found = true
				break
			}
		}
		if !found {
			return fmt.Errorf("copied profile index is missing profile %q", profile.ID)
		}
		path := filepath.Join(root, "profiles", profile.ID, "chainport.db")
		if profile.ID == "default" {
			path = filepath.Join(root, "chainport.db")
		}
		db, err := store.OpenSQLite(path)
		if err != nil {
			return fmt.Errorf("open copied profile %q: %w", profile.Name, err)
		}
		workspace, loadErr := db.Load(context.Background())
		if loadErr == nil {
			loadErr = workspace.Validate()
		}
		closeErr := db.Close()
		if loadErr != nil {
			return fmt.Errorf("validate copied profile %q: %w", profile.Name, loadErr)
		}
		if closeErr != nil {
			return closeErr
		}
	}
	return nil
}

func (m *Manager) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.active == nil {
		return nil
	}
	err := m.active.Close()
	m.active = nil
	return err
}

func (m *Manager) hasProfile(id string) bool {
	for _, p := range m.manifest.Profiles {
		if p.ID == id {
			return true
		}
	}
	return false
}
func (m *Manager) saveManifest() error {
	data, err := json.MarshalIndent(m.manifest, "", "  ")
	if err != nil {
		return err
	}
	return atomicWrite(filepath.Join(m.root, "profiles.json"), data, 0o600)
}
func randomID() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	return hex.EncodeToString(b[:]), nil
}
func samePath(a, b string) bool {
	a, _ = filepath.Abs(a)
	b, _ = filepath.Abs(b)
	return filepath.Clean(a) == filepath.Clean(b)
}
func pathWithin(parent, child string) bool {
	rel, err := filepath.Rel(parent, child)
	return err == nil && (rel == "." || rel != ".." && !strings.HasPrefix(rel, ".."+string(os.PathSeparator)))
}

func writeLocation(path, root string) error {
	data, err := json.Marshal(struct {
		Root string `json:"root"`
	}{root})
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	return atomicWrite(path, data, 0o600)
}
func atomicWrite(path string, data []byte, mode os.FileMode) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), ".chainport-*")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	if err := tmp.Chmod(mode); err != nil {
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
	return replaceFile(name, path)
}

func copyDirectory(source, destination string) error {
	if err := os.MkdirAll(destination, 0o700); err != nil {
		return err
	}
	return filepath.Walk(source, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(source, path)
		if err != nil {
			return err
		}
		if rel == "." {
			return nil
		}
		target := filepath.Join(destination, rel)
		if info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("refusing to copy symlink %q", rel)
		}
		if info.IsDir() {
			return os.MkdirAll(target, 0o700)
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("refusing to copy non-regular file %q", rel)
		}
		in, err := os.Open(path)
		if err != nil {
			return err
		}
		defer in.Close()
		out, err := os.OpenFile(target, os.O_CREATE|os.O_EXCL|os.O_WRONLY, info.Mode().Perm()&0o600)
		if err != nil {
			return err
		}
		_, copyErr := io.Copy(out, in)
		syncErr := out.Sync()
		closeErr := out.Close()
		if copyErr != nil {
			return copyErr
		}
		if syncErr != nil {
			return syncErr
		}
		return closeErr
	})
}
