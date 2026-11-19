package security

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/base64"
	"errors"
	"io"

	"github.com/go-keyring/keyring"
)

var ErrUnavailable = errors.New("the operating system credential vault is unavailable")

type SecretStore interface {
	Put(ctx context.Context, reference, value string) error
	Get(ctx context.Context, reference string) (string, error)
	Delete(ctx context.Context, reference string) error
	Available() bool
}

type OSKeyringStore struct{ serviceName string }

func NewOSKeyringStore() *OSKeyringStore { return &OSKeyringStore{serviceName: "ChainPort Gateway"} }

func (s *OSKeyringStore) Available() bool { return keyring.Available() }

func (s *OSKeyringStore) Put(_ context.Context, reference, value string) error {
	if !s.Available() {
		return ErrUnavailable
	}
	return keyring.Set(s.serviceName, reference, []byte(value))
}

func (s *OSKeyringStore) Get(_ context.Context, reference string) (string, error) {
	if !s.Available() {
		return "", ErrUnavailable
	}
	value, err := keyring.Get(s.serviceName, reference)
	if err != nil {
		return "", err
	}
	return string(value), nil
}

func (s *OSKeyringStore) Delete(_ context.Context, reference string) error {
	if !s.Available() {
		return ErrUnavailable
	}
	return keyring.Delete(s.serviceName, reference)
}

// EncodeMetadataJSON compresses protocol-specific source metadata before placing
// it in platform credential vaults with relatively small per-item limits.
func EncodeMetadataJSON(data []byte) (string, error) {
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	if _, err := writer.Write(data); err != nil {
		return "", err
	}
	if err := writer.Close(); err != nil {
		return "", err
	}
	return "chainport:gzip:" + base64.RawStdEncoding.EncodeToString(buffer.Bytes()), nil
}

func DecodeMetadataJSON(value string) ([]byte, error) {
	const prefix = "chainport:gzip:"
	if len(value) < len(prefix) || value[:len(prefix)] != prefix {
		return nil, errors.New("unsupported metadata encoding")
	}
	compressed, err := base64.RawStdEncoding.DecodeString(value[len(prefix):])
	if err != nil {
		return nil, err
	}
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	return io.ReadAll(io.LimitReader(reader, 4*1024*1024))
}
