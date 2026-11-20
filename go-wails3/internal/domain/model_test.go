package domain

import "testing"

func TestValidatePreservesOrderedMultiHopTUN(t *testing.T) {
	w := DefaultWorkspace()
	w.Nodes = []Node{{ID: "entry", Name: "Entry", Protocol: ProtocolVLESS, Server: "entry.example", Port: 443}, {ID: "exit", Name: "Exit", Protocol: ProtocolSOCKS5, Server: "exit.example", Port: 1080}}
	w.Chains = []Chain{{ID: "route", Name: "Entry to Exit", HopNodeIDs: []string{"entry", "exit"}}}
	w.PortBindings = []PortBinding{{ID: "port-route", ChainID: "route", ListenHost: "127.0.0.1", ListenPort: 20001}}
	w.TUN = TUNBinding{Kind: TUNBindingChain, TargetID: "route"}
	if err := w.Validate(); err != nil {
		t.Fatal(err)
	}
	if w.Chains[0].HopNodeIDs[0] != "entry" || w.Chains[0].HopNodeIDs[1] != "exit" {
		t.Fatal("chain hop order changed")
	}
}

func TestValidateRejectsDuplicateListenerPorts(t *testing.T) {
	w := DefaultWorkspace()
	w.Nodes = []Node{{ID: "n", Name: "Node", Protocol: ProtocolSOCKS5, Server: "localhost", Port: 1080}}
	w.Chains = []Chain{{ID: "c", Name: "Chain", HopNodeIDs: []string{"n"}}}
	w.PortBindings = []PortBinding{{ID: "p", ChainID: "c", ListenHost: "127.0.0.1", ListenPort: w.Settings.BaseListenPort}}
	if err := w.Validate(); err == nil {
		t.Fatal("expected base/chain port collision to fail validation")
	}
}

func TestValidateRejectsLANExposureWithoutOptIn(t *testing.T) {
	w := DefaultWorkspace()
	w.Settings.BaseListenHost = "0.0.0.0"
	if err := w.Validate(); err == nil {
		t.Fatal("wildcard Base listener must be rejected when LAN access is disabled")
	}
	w.Settings.Network.AllowLAN = true
	if err := w.Validate(); err != nil {
		t.Fatalf("explicit LAN access should allow wildcard listener: %v", err)
	}
}

func TestValidateRejectsMalformedXrayFragmentRanges(t *testing.T) {
	w := DefaultWorkspace()
	w.Settings.Network.EnableFinalFragment = true
	w.Settings.Network.XrayFragmentLengths = []string{"100-50"}
	if err := w.Validate(); err == nil {
		t.Fatal("reversed fragment range should fail validation")
	}
	w.Settings.Network.XrayFragmentLengths = []string{"50-100"}
	w.Settings.Network.XrayFragmentDelays = []string{"-1-10"}
	if err := w.Validate(); err == nil {
		t.Fatal("negative fragment delay should fail validation")
	}
}

func TestValidateRequiresUniqueNodeGroupsAndValidAssignments(t *testing.T) {
	w := DefaultWorkspace()
	w.Groups = []NodeGroup{{ID: "group-a", Name: "Work"}, {ID: "group-b", Name: "Personal"}}
	w.Nodes = []Node{{ID: "node", Name: "Node", Protocol: ProtocolSOCKS5, Server: "localhost", Port: 1080, GroupID: "group-a"}}
	if err := w.Validate(); err != nil {
		t.Fatal(err)
	}
	w.Groups = append(w.Groups, NodeGroup{ID: "group-c", Name: "work"})
	if err := w.Validate(); err == nil {
		t.Fatal("expected case-insensitive duplicate group name to fail")
	}
	w.Groups = w.Groups[:2]
	w.Nodes[0].GroupID = "missing"
	if err := w.Validate(); err == nil {
		t.Fatal("expected dangling node group assignment to fail")
	}
}

func TestValidateAllowsNodeAssignmentToSubscriptionGroup(t *testing.T) {
	w := DefaultWorkspace()
	w.Subscriptions = []Subscription{{ID: "subscription-a", Name: "Feed A"}}
	w.Nodes = []Node{{ID: "node-a", Name: "Manual node", Protocol: ProtocolSOCKS5, Server: "localhost", Port: 1080, GroupID: "subscription-a"}}
	if err := w.Validate(); err != nil {
		t.Fatalf("manual node should be allowed in a subscription group: %v", err)
	}
}
