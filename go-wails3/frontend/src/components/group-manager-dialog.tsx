import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { NodeGroup } from "../../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

interface GroupManagerDialogProps {
  open: boolean;
  groups: NodeGroup[];
  onOpenChange: (open: boolean) => void;
  onCreate: (name: string) => Promise<void>;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

export function GroupManagerDialog({ open, groups, onOpenChange, onCreate, onRename, onDelete }: GroupManagerDialogProps) {
  const [newName, setNewName] = useState("");
  const [names, setNames] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setNames(Object.fromEntries(groups.map((group) => [group.id, group.name])));
    setNewName("");
    setError(null);
  }, [open, groups]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await action(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setBusy(false); }
  };

  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="group-manager-dialog" showCloseButton>
      <div className="dialog-heading"><div><DialogTitle>Manage Node Groups</DialogTitle><DialogDescription>Create your own groups and assign Base Nodes from the node editor. Subscription source groups remain separate.</DialogDescription></div></div>
      <form className="group-create-row" onSubmit={(event) => { event.preventDefault(); const name = newName.trim(); if (!name) return; void run(async () => { await onCreate(name); setNewName(""); }); }}>
        <Input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="New group name" aria-label="New group name" />
        <Button type="submit" disabled={busy || !newName.trim()}><Plus size={14}/> Create Group</Button>
      </form>
      <div className="group-manager-list">
        {groups.map((group) => <div className="group-manager-row" key={group.id}>
          <Input aria-label={`${group.name} group name`} value={names[group.id] ?? group.name} onChange={(event) => setNames((current) => ({ ...current, [group.id]: event.target.value }))} />
          <Button size="sm" variant="outline" disabled={busy || !(names[group.id] ?? group.name).trim() || (names[group.id] ?? group.name).trim() === group.name} onClick={() => void run(() => onRename(group.id, (names[group.id] ?? group.name).trim()))}>Rename</Button>
          <Button size="icon" variant="ghost" disabled={busy} aria-label={`Delete ${group.name}`} title="Delete group" onClick={() => { if (window.confirm(`Delete group "${group.name}"? Nodes will remain and become ungrouped.`)) void run(() => onDelete(group.id)); }}><Trash2 size={15}/></Button>
        </div>)}
        {groups.length === 0 && <div className="empty-state group-empty"><strong>No custom groups yet</strong><span>Create a group, then assign nodes to it from Edit Node.</span></div>}
      </div>
      {error && <div className="error-panel dialog-error">{error}</div>}
      <div className="dialog-actions"><Button variant="outline" onClick={() => onOpenChange(false)}>Done</Button></div>
    </DialogContent>
  </Dialog>;
}
