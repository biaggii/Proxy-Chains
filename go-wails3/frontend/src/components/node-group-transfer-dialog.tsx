import { useEffect, useState } from "react";
import { Copy, FolderInput } from "lucide-react";
import type { NodeGroup } from "../../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FloatingDialog } from "@/components/floating-dialog";

interface Props {
  open: boolean;
  mode: "move" | "copy";
  nodeName: string;
  groups: NodeGroup[];
  onOpenChange: (open: boolean) => void;
  onConfirm: (groupID: string) => Promise<void>;
}

export function NodeGroupTransferDialog({ open, mode, nodeName, groups, onOpenChange, onConfirm }: Props) {
  const [groupID, setGroupID] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setGroupID(groups[0]?.id ?? "");
    setError(null);
    setBusy(false);
  }, [open, groups]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!groupID) return;
    setBusy(true);
    setError(null);
    try {
      await onConfirm(groupID);
      onOpenChange(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return <FloatingDialog open={open} onOpenChange={onOpenChange} title={mode === "move" ? "Move Node to Group" : "Copy Node to Group"} description={mode === "move" ? `Move “${nodeName}” into another group. The node keeps its ID and Chain references.` : `Create an independent copy of “${nodeName}” in another group. Credentials are copied through the OS credential vault.`} className="node-group-transfer-dialog" initialWidth={520} minWidth={360} minHeight={260}>
    <form onSubmit={submit}>
      <label className="form-label">Destination group
        <Select value={groupID} onValueChange={(value) => setGroupID(String(value))}>
          <SelectTrigger className="native-select"><SelectValue placeholder="Choose a group" /></SelectTrigger>
          <SelectContent>{groups.map((group) => <SelectItem key={group.id} value={group.id}>{group.name}</SelectItem>)}</SelectContent>
        </Select>
      </label>
      {error && <div className="error-panel dialog-error">{error}</div>}
      <div className="dialog-actions">
        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button type="submit" disabled={busy || !groupID}>{busy ? "Working…" : mode === "move" ? <><FolderInput size={14}/> Move Node</> : <><Copy size={14}/> Copy Node</>}</Button>
      </div>
    </form>
  </FloatingDialog>;
}
