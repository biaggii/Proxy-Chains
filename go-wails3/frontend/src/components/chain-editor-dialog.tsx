import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowRight, ArrowUp, Search, X } from "lucide-react";
import type { Chain, Node } from "../../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

interface ChainEditorDialogProps {
  open: boolean;
  nodes: Node[];
  chain?: Chain;
  listenPort?: number;
  onOpenChange: (open: boolean) => void;
  onSave: (input: { id?: string; name: string; hopNodeIds: string[]; listenPort: number }) => Promise<void>;
}

export function ChainEditorDialog({ open, nodes, chain, listenPort, onOpenChange, onSave }: ChainEditorDialogProps) {
  const [name, setName] = useState("");
  const [port, setPort] = useState("20001");
  const [hopNodeIds, setHopNodeIds] = useState<string[]>([]);
  const [availableSelection, setAvailableSelection] = useState<string | null>(null);
  const [hopSelection, setHopSelection] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(chain?.name ?? "");
    setPort(String(listenPort ?? 20001));
    setHopNodeIds([...(chain?.hopNodeIds ?? [])]);
    setAvailableSelection(null);
    setHopSelection(chain?.hopNodeIds?.[0] ?? null);
    setSearch("");
    setFormError(null);
  }, [chain, listenPort, open]);

  const availableNodes = useMemo(() => {
    const selected = new Set(hopNodeIds);
    const query = search.trim().toLocaleLowerCase();
    return nodes.filter((node) => !selected.has(node.id) && (!query || [node.name, node.protocol, node.server].some((value) => value.toLocaleLowerCase().includes(query))));
  }, [hopNodeIds, nodes, search]);

  const addSelectedNode = () => {
    if (!availableSelection || hopNodeIds.includes(availableSelection)) return;
    setHopNodeIds((current) => [...current, availableSelection]);
    setHopSelection(availableSelection);
    setAvailableSelection(null);
  };

  const removeSelectedHop = () => {
    if (!hopSelection) return;
    const index = hopNodeIds.indexOf(hopSelection);
    setHopNodeIds((current) => current.filter((id) => id !== hopSelection));
    setHopSelection(hopNodeIds[index + 1] ?? hopNodeIds[index - 1] ?? null);
  };

  const moveSelectedHop = (direction: -1 | 1) => {
    if (!hopSelection) return;
    const index = hopNodeIds.indexOf(hopSelection);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= hopNodeIds.length) return;
    setHopNodeIds((current) => {
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedPort = Number(port);
    if (!name.trim() || hopNodeIds.length === 0 || !Number.isInteger(parsedPort) || parsedPort < 1 || parsedPort > 65535) return;
    setSaving(true);
    try {
      await onSave({ id: chain?.id, name: name.trim(), hopNodeIds, listenPort: parsedPort });
      onOpenChange(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  };

  const nodeSummary = (node: Node) => `${node.protocol} · ${node.server}:${node.port}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="dialog-content chain-editor-dialog" showCloseButton={false}>
        <div className="dialog-heading">
          <div><DialogTitle>{chain ? "Edit Chain" : "Create Chain"}</DialogTitle><DialogDescription>Build the route from Entry to Exit. Add Base Nodes, then arrange their order.</DialogDescription></div>
          <DialogClose render={<Button variant="ghost" size="icon" aria-label="Close" />}><X size={17} /></DialogClose>
        </div>
        <form onSubmit={submit}>
          <div className="chain-name-port">
            <label className="form-label chain-name-field">Name<Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Chain name" autoFocus /></label>
            <label className="form-label chain-port-field">Local Port<Input type="number" min={1} max={65535} value={port} onChange={(event) => setPort(event.target.value)} /></label>
          </div>

          <div className="chain-builder-grid">
            <section className="chain-builder-column">
              <div className="chain-builder-heading"><strong>Available Base Nodes</strong><span>{availableNodes.length} available</span></div>
              <div className="chain-node-search"><Search size={14}/><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search nodes by name, address or protocol" aria-label="Search available nodes"/></div>
              <div className="chain-node-list" role="listbox" aria-label="Available Base Nodes">
                {availableNodes.map((node) => <button type="button" role="option" aria-selected={availableSelection === node.id} className="chain-node-option" key={node.id} onClick={() => setAvailableSelection(node.id)} onDoubleClick={addSelectedNode}>
                  <span className="chain-node-name">{node.name}</span><span className="chain-node-summary">{nodeSummary(node)}</span>
                </button>)}
                {availableNodes.length === 0 && <div className="chain-list-empty">{nodes.length === 0 ? "No Base Nodes available." : search ? "No matching nodes." : "All available nodes are already in this Chain."}</div>}
              </div>
              <Button type="button" variant="outline" className="chain-add-button" disabled={!availableSelection} onClick={addSelectedNode}>Add selected node <ArrowRight size={15}/></Button>
            </section>

            <section className="chain-builder-column">
              <div className="chain-builder-heading"><strong>Chain Hops · Entry → Exit</strong><span>{hopNodeIds.length} hop(s)</span></div>
              <div className="chain-hop-list" role="listbox" aria-label="Chain hops">
                {hopNodeIds.map((id, index) => {
                  const node = nodes.find((item) => item.id === id);
                  return <button type="button" role="option" aria-selected={hopSelection === id} className="chain-hop-option" key={id} onClick={() => setHopSelection(id)}>
                    <span className="chain-hop-number">{index + 1}</span>
                    <span className="chain-hop-copy"><strong>{node?.name ?? "Missing node"}</strong><small>{node ? nodeSummary(node) : id}</small></span>
                    <span className="chain-hop-role">{index === 0 ? "ENTRY" : index === hopNodeIds.length - 1 ? "EXIT" : "HOP"}</span>
                  </button>;
                })}
                {hopNodeIds.length === 0 && <div className="chain-list-empty">Select a node on the left and choose Add to build the route.</div>}
              </div>
              <div className="chain-hop-actions">
                <Button type="button" variant="outline" disabled={!hopSelection} onClick={removeSelectedHop}>Remove</Button>
                <Button type="button" variant="outline" disabled={!hopSelection || hopNodeIds.indexOf(hopSelection) <= 0} onClick={() => moveSelectedHop(-1)}><ArrowUp size={14}/> Move Up</Button>
                <Button type="button" variant="outline" disabled={!hopSelection || hopNodeIds.indexOf(hopSelection) < 0 || hopNodeIds.indexOf(hopSelection) === hopNodeIds.length - 1} onClick={() => moveSelectedHop(1)}><ArrowDown size={14}/> Move Down</Button>
              </div>
            </section>
          </div>
          {formError && <div className="error-panel dialog-error">{formError}</div>}
          <div className="dialog-actions"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={saving || !name.trim() || hopNodeIds.length === 0 || !Number.isInteger(Number(port)) || Number(port) < 1 || Number(port) > 65535}>{saving ? "Saving…" : chain ? "Save Changes" : "Create Chain"}</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
