package store

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/biaggii/Proxy-Chains/go-wails3/internal/domain"
)

func TestSQLiteRoundTripAndPortUniqueness(t *testing.T) {
	s, err := OpenSQLite(filepath.Join(t.TempDir(), "chainport.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	w := domain.DefaultWorkspace()
	w.Nodes = []domain.Node{{ID: "node-a", Name: "Entry", Protocol: domain.ProtocolSOCKS5, Server: "127.0.0.1", Port: 1080, Transport: domain.Transport{Network: "tcp"}}}
	w.Groups = []domain.NodeGroup{{ID: "group-a", Name: "Work"}}
	w.Nodes[0].GroupID = "group-a"
	w.Chains = []domain.Chain{{ID: "chain-a", Name: "Route", HopNodeIDs: []string{"node-a"}}}
	w.PortBindings = []domain.PortBinding{{ID: "binding-a", ChainID: "chain-a", ListenHost: "127.0.0.1", ListenPort: 20001}}
	w.ActiveNodeID = "node-a"
	w.TUN = domain.TUNBinding{Kind: domain.TUNBindingChain, TargetID: "chain-a"}
	if err := s.Save(context.Background(), w); err != nil {
		t.Fatal(err)
	}
	got, err := s.Load(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Nodes) != 1 || len(got.Chains) != 1 || len(got.PortBindings) != 1 || len(got.Groups) != 1 || got.Nodes[0].GroupID != "group-a" {
		t.Fatalf("unexpected loaded workspace: %+v", got)
	}
	if got.PortBindings[0].ListenPort != 20001 || got.ActiveNodeID != "node-a" || got.TUN.Kind != domain.TUNBindingChain || got.TUN.TargetID != "chain-a" {
		t.Fatalf("unexpected loaded port or active node: %+v", got)
	}
}
