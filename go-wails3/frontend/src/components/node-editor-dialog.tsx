import { useEffect, useState } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { Clipboard } from "@wailsio/runtime";
import type { Node, NodeGroup, Subscription } from "../../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FloatingDialog } from "@/components/floating-dialog";

export interface NodeEditorInput {
  id?: string;
  name: string;
  protocol?: string;
  server: string;
  port: number;
  username: string;
  password: string;
  network: string;
  path: string;
  host: string;
  tls: boolean;
  insecure: boolean;
  sni: string;
  alpn: string[];
  groupId: string;
}

interface NodeEditorDialogProps {
  open: boolean;
  node?: Node;
  groups: NodeGroup[];
  subscriptions: Subscription[];
  credentials?: { username: string; password: string };
  initialGroupId?: string;
  onOpenChange: (open: boolean) => void;
  onSave: (input: NodeEditorInput) => Promise<void>;
}

export function NodeEditorDialog({ open, node, groups, subscriptions, credentials, initialGroupId, onOpenChange, onSave }: NodeEditorDialogProps) {
  const [name, setName] = useState("");
  const [protocol, setProtocol] = useState("socks5");
  const [server, setServer] = useState("");
  const [port, setPort] = useState("1080");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [passwordCopied, setPasswordCopied] = useState(false);
  const [network, setNetwork] = useState("tcp");
  const [path, setPath] = useState("");
  const [host, setHost] = useState("");
  const [tls, setTLS] = useState(false);
  const [insecure, setInsecure] = useState(false);
  const [sni, setSNI] = useState("");
  const [alpn, setALPN] = useState("");
  const [groupId, setGroupId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canEditProtocol = !node || node.protocol === "socks5" || node.protocol === "http";
  const supportsUserPassword = protocol === "socks5" || protocol === "http" || protocol === "https";

  useEffect(() => {
    if (!open) return;
    const initialProtocol = node?.protocol === "http" && node.tls?.enabled ? "https" : node?.protocol ?? "socks5";
    setName(node?.name ?? "");
    setProtocol(initialProtocol);
    setServer(node?.server ?? "");
    setPort(String(node?.port ?? 1080));
    setUsername(credentials?.username ?? "");
    setPassword(credentials?.password ?? "");
    setShowPassword(false);
    setPasswordCopied(false);
    setGroupId(node?.groupId ?? initialGroupId ?? "");
    setNetwork(node?.transport?.network || "tcp");
    setPath(node?.transport?.path || "");
    setHost(node?.transport?.host || "");
    setTLS(node?.tls?.enabled ?? false);
    setInsecure(node?.tls?.insecure ?? false);
    setSNI(node?.tls?.sni || "");
    setALPN((node?.tls?.alpn ?? []).join(", "));
    setError(null);
  }, [open, node, credentials, initialGroupId]);

  const changeProtocol = (value: string) => {
    setProtocol(value);
    setTLS(value === "https");
    if (value !== "https") setInsecure(false);
  };

  const changeTLS = (enabled: boolean) => {
    setTLS(enabled);
    if (!enabled) setInsecure(false);
    if (protocol === "http" || protocol === "https") setProtocol(enabled ? "https" : "http");
  };

  const copyPassword = async () => {
    if (!password) return;
    try {
      await Clipboard.SetText(password);
      setPasswordCopied(true);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? `Could not copy password: ${cause.message}` : "Could not copy password to the clipboard.");
    }
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedPort = Number(port);
    if (!name.trim() || !server.trim() || !Number.isInteger(parsedPort) || parsedPort < 1 || parsedPort > 65535) return;
    setSaving(true);
    try {
      await onSave({
        id: node?.id,
        name: name.trim(),
        protocol: canEditProtocol ? (protocol === "socks5" ? "socks5" : "http") : undefined,
        server: server.trim(),
        port: parsedPort,
        username,
        password,
        network: network.trim() || "tcp",
        path,
        host,
        tls: protocol === "https" ? true : tls,
        insecure,
        sni,
        alpn: alpn.split(",").map((value) => value.trim()).filter(Boolean),
        groupId,
      });
      onOpenChange(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <FloatingDialog open={open} onOpenChange={onOpenChange} title={node ? "Edit Base Node" : "Add Base Node"} description={node ? "Edit node details. Credentials are stored in the OS credential vault." : "Create a SOCKS5, HTTP or HTTPS proxy node."} className="node-editor-dialog" initialWidth={680} minWidth={500} minHeight={420}>
        <form onSubmit={submit}>
          <label className="form-label">Name<Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Node name" autoFocus /></label>
          <label className="form-label">Protocol
            {canEditProtocol ? (
              <Select value={protocol} onValueChange={(value) => changeProtocol(String(value))}>
                <SelectTrigger className="native-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="socks5">SOCKS5</SelectItem>
                  <SelectItem value="http">HTTP</SelectItem>
                  <SelectItem value="https">HTTPS</SelectItem>
                </SelectContent>
              </Select>
            ) : <Input value={node?.protocol.toUpperCase() ?? protocol.toUpperCase()} disabled />}
            {node && !canEditProtocol && <span className="form-hint">Imported protocol is preserved. Edit its endpoint and metadata without changing its protocol credentials.</span>}
          </label>
          <div className="form-grid node-endpoint-grid">
            <label className="form-label">Server<Input value={server} onChange={(event) => setServer(event.target.value)} placeholder="proxy.example.com" /></label>
            <label className="form-label">Port<Input type="number" min={1} max={65535} value={port} onChange={(event) => setPort(event.target.value)} /></label>
          </div>
          {supportsUserPassword && <>
            <div className="form-grid node-credentials-grid">
              <label className="form-label">Username (optional)<Input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="off" /></label>
              <label className="form-label">Password (optional)
                <div className="password-control">
                  <Input type={showPassword ? "text" : "password"} value={password} onChange={(event) => { setPassword(event.target.value); setPasswordCopied(false); }} autoComplete="new-password" />
                  <Button type="button" size="icon" variant="outline" disabled={!password} title={showPassword ? "Hide password" : "Show password"} aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff size={15} /> : <Eye size={15} />}</Button>
                  <Button type="button" size="icon" variant="outline" disabled={!password} title="Copy password" aria-label="Copy password" onClick={() => void copyPassword()}>{passwordCopied ? <Check size={15} /> : <Copy size={15} />}</Button>
                </div>
              </label>
            </div>
            <p className="form-hint">Saved credentials are loaded from the OS credential vault. Leave a field empty to clear that credential.</p>
          </>}
          {!supportsUserPassword && node && <p className="form-hint">Credentials for {protocol} remain protected in the OS credential vault and are not exposed in this editor.</p>}
          <label className="form-label">Node group
            <Select value={groupId || "none"} onValueChange={(value) => setGroupId(value === "none" ? "" : String(value))}>
              <SelectTrigger className="native-select"><SelectValue placeholder="No group" /></SelectTrigger>
              <SelectContent><SelectItem value="none">No group</SelectItem>{groups.map((group) => <SelectItem key={`custom-${group.id}`} value={group.id}>{group.name} · Custom</SelectItem>)}{subscriptions.map((subscription) => <SelectItem key={`subscription-${subscription.id}`} value={subscription.id}>{subscription.name} · Subscription</SelectItem>)}</SelectContent>
            </Select>
          </label>

          <details className="node-advanced-options">
            <summary>Advanced options</summary>
            <div className="node-advanced-content">
              <div className="form-grid">
                <label className="form-label">Transport<Input value={network} onChange={(event) => setNetwork(event.target.value)} placeholder="tcp / ws / grpc" /></label>
                <label className="form-label">TLS SNI<Input value={sni} onChange={(event) => setSNI(event.target.value)} placeholder="server name" /></label>
              </div>
              {protocol !== "socks5" && <label className="setting-toggle"><span>TLS enabled</span><input type="checkbox" checked={protocol === "https" || tls} onChange={(event) => changeTLS(event.target.checked)} /></label>}
              <label className="setting-toggle"><span>Allow insecure TLS certificate</span><input type="checkbox" checked={insecure} onChange={(event) => setInsecure(event.target.checked)} /></label>
              <label className="form-label">ALPN (comma separated)<Input value={alpn} onChange={(event) => setALPN(event.target.value)} placeholder="h2, http/1.1" /></label>
              <div className="form-grid">
                <label className="form-label">Transport path<Input value={path} onChange={(event) => setPath(event.target.value)} placeholder="/" /></label>
                <label className="form-label">Transport host<Input value={host} onChange={(event) => setHost(event.target.value)} placeholder="Host header" /></label>
              </div>
            </div>
          </details>
          {error && <div className="error-panel dialog-error">{error}</div>}
          <div className="dialog-actions">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={saving || !name.trim() || !server.trim() || !Number.isInteger(Number(port)) || Number(port) < 1 || Number(port) > 65535}>{saving ? "Saving…" : node ? "Save Changes" : "Add Node"}</Button>
          </div>
        </form>
    </FloatingDialog>
  );
}
