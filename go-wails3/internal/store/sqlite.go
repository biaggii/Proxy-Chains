package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	_ "modernc.org/sqlite"
)

type SQLiteStore struct{ db *sql.DB }

type workspacePreferences struct {
	Groups       []domain.NodeGroup `json:"groups,omitempty"`
	Settings     domain.Settings    `json:"settings"`
	ActiveNodeID string             `json:"activeNodeId,omitempty"`
	TUN          domain.TUNBinding  `json:"tun"`
}

func OpenSQLite(path string) (*SQLiteStore, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("create database directory: %w", err)
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, fmt.Errorf("create database file: %w", err)
	}
	if err := file.Close(); err != nil {
		return nil, fmt.Errorf("close database file: %w", err)
	}
	if err := os.Chmod(path, 0o600); err != nil {
		return nil, fmt.Errorf("restrict database file permissions: %w", err)
	}
	db, err := sql.Open("sqlite", path+"?_pragma=foreign_keys(1)&_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)")
	if err != nil {
		return nil, fmt.Errorf("open SQLite database: %w", err)
	}
	db.SetMaxOpenConns(1)
	s := &SQLiteStore{db: db}
	if err := s.migrate(context.Background()); err != nil {
		_ = db.Close()
		return nil, err
	}
	return s, nil
}

func (s *SQLiteStore) Close() error { return s.db.Close() }

func (s *SQLiteStore) migrate(ctx context.Context) error {
	statements := []string{
		`CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)`,
		`CREATE TABLE IF NOT EXISTS workspace_settings (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS subscriptions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, payload TEXT NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS chains (id TEXT PRIMARY KEY, payload TEXT NOT NULL)`,
		`CREATE TABLE IF NOT EXISTS port_bindings (id TEXT PRIMARY KEY, chain_id TEXT NOT NULL REFERENCES chains(id) ON DELETE CASCADE, listen_port INTEGER NOT NULL UNIQUE, payload TEXT NOT NULL)`,
		`INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)`,
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, statement := range statements {
		if _, err := tx.ExecContext(ctx, statement); err != nil {
			return fmt.Errorf("apply SQLite migration: %w", err)
		}
	}
	return tx.Commit()
}

func (s *SQLiteStore) Load(ctx context.Context) (domain.Workspace, error) {
	w := domain.DefaultWorkspace()
	var settings string
	err := s.db.QueryRowContext(ctx, `SELECT payload FROM workspace_settings WHERE id=1`).Scan(&settings)
	if err != nil && err != sql.ErrNoRows {
		return w, fmt.Errorf("load workspace settings: %w", err)
	}
	if err == nil {
		var preferences workspacePreferences
		if err := json.Unmarshal([]byte(settings), &preferences); err != nil {
			return w, fmt.Errorf("decode workspace settings: %w", err)
		}
		w.Settings, w.ActiveNodeID, w.TUN = preferences.Settings, preferences.ActiveNodeID, preferences.TUN
		w.Groups = preferences.Groups
		if w.Groups == nil {
			w.Groups = []domain.NodeGroup{}
		}
	}
	if err := loadRows(ctx, s.db, `SELECT payload FROM subscriptions ORDER BY rowid`, &w.Subscriptions); err != nil {
		return w, err
	}
	if err := loadRows(ctx, s.db, `SELECT payload FROM nodes ORDER BY rowid`, &w.Nodes); err != nil {
		return w, err
	}
	if err := loadRows(ctx, s.db, `SELECT payload FROM chains ORDER BY rowid`, &w.Chains); err != nil {
		return w, err
	}
	if err := loadRows(ctx, s.db, `SELECT payload FROM port_bindings ORDER BY rowid`, &w.PortBindings); err != nil {
		return w, err
	}
	return w, nil
}

func loadRows[T any](ctx context.Context, db *sql.DB, query string, target *[]T) error {
	rows, err := db.QueryContext(ctx, query)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var payload string
		if err := rows.Scan(&payload); err != nil {
			return err
		}
		var value T
		if err := json.Unmarshal([]byte(payload), &value); err != nil {
			return fmt.Errorf("decode %s row: %w", query, err)
		}
		*target = append(*target, value)
	}
	return rows.Err()
}

func (s *SQLiteStore) Save(ctx context.Context, w domain.Workspace) error {
	if err := w.Validate(); err != nil {
		return fmt.Errorf("validate workspace before save: %w", err)
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, table := range []string{"port_bindings", "chains", "nodes", "subscriptions"} {
		if _, err := tx.ExecContext(ctx, `DELETE FROM `+table); err != nil {
			return err
		}
	}
	settings, err := json.Marshal(workspacePreferences{Groups: w.Groups, Settings: w.Settings, ActiveNodeID: w.ActiveNodeID, TUN: w.TUN})
	if err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, `INSERT INTO workspace_settings(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload`, string(settings)); err != nil {
		return err
	}
	for _, item := range w.Subscriptions {
		if err := insertJSON(ctx, tx, `INSERT INTO subscriptions(id,payload) VALUES(?,?)`, item.ID, item); err != nil {
			return err
		}
	}
	for _, item := range w.Nodes {
		if err := insertJSON(ctx, tx, `INSERT INTO nodes(id,payload) VALUES(?,?)`, item.ID, item); err != nil {
			return err
		}
	}
	for _, item := range w.Chains {
		if err := insertJSON(ctx, tx, `INSERT INTO chains(id,payload) VALUES(?,?)`, item.ID, item); err != nil {
			return err
		}
	}
	for _, item := range w.PortBindings {
		payload, err := json.Marshal(item)
		if err != nil {
			return err
		}
		if _, err := tx.ExecContext(ctx, `INSERT INTO port_bindings(id,chain_id,listen_port,payload) VALUES(?,?,?,?)`, item.ID, item.ChainID, item.ListenPort, string(payload)); err != nil {
			return fmt.Errorf("insert port binding %s: %w", item.ID, err)
		}
	}
	return tx.Commit()
}

func insertJSON[T any](ctx context.Context, tx *sql.Tx, query, id string, item T) error {
	payload, err := json.Marshal(item)
	if err != nil {
		return err
	}
	if _, err := tx.ExecContext(ctx, query, id, string(payload)); err != nil {
		return fmt.Errorf("insert %s: %w", id, err)
	}
	return nil
}
