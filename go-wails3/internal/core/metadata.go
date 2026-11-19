package core

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
	"github.com/biaggii/Proxy-Chains/go-wails3/internal/security"
)

// ResolveNodeExtra loads the legacy parser's protocol-specific `extra` object
// from the OS credential vault. It is intentionally backend-only: these fields
// can contain credentials and must not be exposed to the React frontend.
func ResolveNodeExtra(ctx context.Context, node domain.Node, secrets security.SecretStore) (map[string]any, error) {
	if node.SourceMetadataRef == "" {
		return map[string]any{}, nil
	}
	if secrets == nil || !secrets.Available() {
		return nil, security.ErrUnavailable
	}
	encoded, err := secrets.Get(ctx, node.SourceMetadataRef)
	if err != nil {
		return nil, err
	}
	data, err := security.DecodeMetadataJSON(encoded)
	if err != nil {
		return nil, err
	}
	var metadata struct {
		Extra map[string]any `json:"extra"`
	}
	if err := json.Unmarshal(data, &metadata); err != nil {
		return nil, err
	}
	if metadata.Extra == nil {
		return nil, errors.New("node protocol metadata does not contain an extra object")
	}
	return metadata.Extra, nil
}

type ResolvedNode struct {
	Domain     domain.Node
	Username   string
	Password   string
	UUID       string
	PrivateKey string
	Extra      map[string]any
}

func ResolveNode(ctx context.Context, node domain.Node, secrets security.SecretStore) (ResolvedNode, error) {
	result := ResolvedNode{Domain: node, Extra: map[string]any{}}
	if node.SourceMetadataRef != "" {
		extra, err := ResolveNodeExtra(ctx, node, secrets)
		if err != nil {
			return result, err
		}
		result.Extra = extra
	}
	refs := []struct {
		ref    string
		target *string
	}{
		{node.Credentials.UsernameRef, &result.Username},
		{node.Credentials.PasswordRef, &result.Password},
		{node.Credentials.UUIDRef, &result.UUID},
		{node.Credentials.PrivateKeyRef, &result.PrivateKey},
	}
	for _, item := range refs {
		if item.ref == "" {
			continue
		}
		if secrets == nil || !secrets.Available() {
			return result, security.ErrUnavailable
		}
		value, err := secrets.Get(ctx, item.ref)
		if err != nil {
			return result, err
		}
		*item.target = value
	}
	return result, nil
}
