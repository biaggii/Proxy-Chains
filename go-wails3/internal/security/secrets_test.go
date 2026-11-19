package security

import (
	"bytes"
	"testing"
)

func TestMetadataCompressionRoundTrip(t *testing.T) {
	original := []byte(`{"plugin":"obfs-local","plugin_opts":{"mode":"tls","host":"example.com"},"query":{"security":"tls"}}`)
	encoded, err := EncodeMetadataJSON(original)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := DecodeMetadataJSON(encoded)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(original, decoded) {
		t.Fatalf("metadata mismatch: %s", decoded)
	}
}
