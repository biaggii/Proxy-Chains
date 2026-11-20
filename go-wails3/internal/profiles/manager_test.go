package profiles

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/store"
)

func TestProfilesCreateSwitchRenameDeleteAndKeepDataSeparate(t *testing.T) {
	root := filepath.Join(t.TempDir(), "data")
	m, err := Open(root, filepath.Join(t.TempDir(), "location.json"))
	if err != nil {
		t.Fatal(err)
	}
	defer m.Close()
	w, err := m.Load(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	w.Nodes = []domain.Node{{ID: "default-node", Name: "Default node", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080}}
	if err := m.Save(context.Background(), w); err != nil {
		t.Fatal(err)
	}
	p, err := m.Create("Work")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := m.Switch(p.ID); err != nil {
		t.Fatal(err)
	}
	work, err := m.Load(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(work.Nodes) != 0 {
		t.Fatal("new profile inherited another profile's nodes")
	}
	work.Nodes = []domain.Node{{ID: "work-node", Name: "Work node", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1081}}
	if err := m.Save(context.Background(), work); err != nil {
		t.Fatal(err)
	}
	if err := m.Rename(p.ID, "Office"); err != nil {
		t.Fatal(err)
	}
	if err := m.Delete(p.ID); err == nil {
		t.Fatal("active profile deletion should fail")
	}
	if _, err := m.Switch("default"); err != nil {
		t.Fatal(err)
	}
	defaultWorkspace, err := m.Load(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(defaultWorkspace.Nodes) != 1 || defaultWorkspace.Nodes[0].ID != "default-node" {
		t.Fatalf("default profile changed: %+v", defaultWorkspace.Nodes)
	}
	if err := m.Delete(p.ID); err != nil {
		t.Fatal(err)
	}
}

func TestOpenExistingSingleDatabaseAsDefaultProfile(t *testing.T) {
	root := filepath.Join(t.TempDir(), "ChainPort Gateway")
	db, err := store.OpenSQLite(filepath.Join(root, "chainport.db"))
	if err != nil {
		t.Fatal(err)
	}
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "legacy-db-node", Name: "Existing", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080}}
	if err := db.Save(context.Background(), w); err != nil {
		t.Fatal(err)
	}
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}
	m, err := Open(root, filepath.Join(t.TempDir(), "location.json"))
	if err != nil {
		t.Fatal(err)
	}
	defer m.Close()
	loaded, err := m.Load(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(loaded.Nodes) != 1 || loaded.Nodes[0].ID != "legacy-db-node" {
		t.Fatalf("existing pre-profile database was not preserved: %+v", loaded.Nodes)
	}
}

func TestMoveDataLocationCopiesProfilesAndPersistsPointer(t *testing.T) {
	base := t.TempDir()
	root := filepath.Join(base, "old")
	pointer := filepath.Join(base, "location.json")
	m, err := Open(root, pointer)
	if err != nil {
		t.Fatal(err)
	}
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "n", Name: "N", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080}}
	if err := m.Save(context.Background(), w); err != nil {
		t.Fatal(err)
	}
	p, err := m.Create("Other")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := m.Switch(p.ID); err != nil {
		t.Fatal(err)
	}
	if err := m.Close(); err != nil {
		t.Fatal(err)
	}
	m, err = Open(root, pointer)
	if err != nil {
		t.Fatal(err)
	}
	defer m.Close()
	destination := filepath.Join(base, "new-data")
	if err := m.MoveDataLocation(destination); err != nil {
		t.Fatal(err)
	}
	if m.State().DataLocation != destination {
		t.Fatalf("wrong data root: %+v", m.State())
	}
	if _, err := os.Stat(filepath.Join(root, "chainport.db")); err != nil {
		t.Fatal("old data should be retained until the new location is verified")
	}
	if err := m.Close(); err != nil {
		t.Fatal(err)
	}
	reopened, err := Open(root, pointer)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	if reopened.State().DataLocation != destination || reopened.State().ActiveProfileID != p.ID {
		t.Fatalf("data location pointer not restored: %+v", reopened.State())
	}
	active, err := reopened.Load(context.Background())
	if err != nil || len(active.Nodes) != 0 {
		t.Fatalf("active profile data not preserved: %+v %v", active.Nodes, err)
	}
}

func TestMoveDataLocationRejectsNonEmptyAndNestedTargets(t *testing.T) {
	base := t.TempDir()
	m, err := Open(filepath.Join(base, "data"), filepath.Join(base, "pointer.json"))
	if err != nil {
		t.Fatal(err)
	}
	defer m.Close()
	if err := m.MoveDataLocation(filepath.Join(base, "data", "nested")); err == nil {
		t.Fatal("nested target must be rejected")
	}
	nonEmpty := filepath.Join(base, "occupied")
	if err := os.MkdirAll(nonEmpty, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(nonEmpty, "keep"), []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := m.MoveDataLocation(nonEmpty); err == nil {
		t.Fatal("non-empty target must be rejected")
	}
}

func TestOpenRejectsUnsafeProfileIDsFromManifest(t *testing.T) {
	root := t.TempDir()
	manifest := []byte(`{"version":1,"activeProfileId":"../../outside","profiles":[{"id":"../../outside","name":"Bad"}]}`)
	if err := os.WriteFile(filepath.Join(root, "profiles.json"), manifest, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(root, filepath.Join(t.TempDir(), "location.json")); err == nil {
		t.Fatal("profile index path traversal must be rejected")
	}
}
