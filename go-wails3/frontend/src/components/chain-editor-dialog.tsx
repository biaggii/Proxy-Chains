import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, X } from "lucide-react";
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
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(chain?.name ?? "");
    setPort(String(listenPort ?? 20001));
    setHopNodeIds([...(chain?.hopNodeIds ?? [])]);
    setFormError(null);
  }, [chain, listenPort, open]);

  const toggleNode = (id: string) => {
    setHopNodeIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  };

  const moveHop = (index: number, direction: -1 | 1) => {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= hopNodeIds.length) return;
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="dialog-content" showCloseButton={false}>
          <div className="dialog-heading"><div><DialogTitle>{chain ? "Edit Chain" : "Create Chain"}</DialogTitle><DialogDescription>Arrange Base Nodes in traffic order: Entry → Exit.</DialogDescription></div><DialogClose render={<Button variant="ghost" size="icon" aria-label="Close" />}><X size={17} /></DialogClose></div>
          <form onSubmit={submit}>
            <label className="form-label">Chain name<Input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Hong Kong → Japan" autoFocus /></label>
            <label className="form-label">Local listener port<Input type="number" min={1} max={65535} value={port} onChange={(event) => setPort(event.target.value)} /></label>
            <div className="form-label">Route hops <span className="form-hint">Select nodes, then arrange Entry → Exit order.</span></div>
            <div className="node-picker">{nodes.map((node) => <label className="node-option" key={node.id}><input type="checkbox" checked={hopNodeIds.includes(node.id)} onChange={() => toggleNode(node.id)} /><span><strong>{node.name}</strong><small>{node.protocol} · {node.server}:{node.port}</small></span></label>)}</div>
            {hopNodeIds.length > 0 && <div className="route-order"><div className="route-order-title">ROUTE ORDER</div>{hopNodeIds.map((id, index) => { const node = nodes.find((item) => item.id === id); return <div className="route-hop" key={id}><span className="route-hop-index">{index + 1}</span><span>{node?.name ?? "Missing node"}</span><div className="route-hop-actions"><Button type="button" variant="ghost" size="icon" disabled={index === 0} onClick={() => moveHop(index, -1)} aria-label="Move hop up"><ArrowUp size={14} /></Button><Button type="button" variant="ghost" size="icon" disabled={index === hopNodeIds.length - 1} onClick={() => moveHop(index, 1)} aria-label="Move hop down"><ArrowDown size={14} /></Button></div></div>; })}</div>}
            {formError && <div className="error-panel dialog-error">{formError}</div>}
            <div className="dialog-actions"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={saving || !name.trim() || hopNodeIds.length === 0}>{saving ? "Saving…" : chain ? "Save Changes" : "Create Chain"}</Button></div>
          </form>
      </DialogContent>
    </Dialog>
  );
}
