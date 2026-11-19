import { useEffect, useState } from "react";
import { X } from "lucide-react";
import type { Node } from "../../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface NodeEditorInput {
  id?: string; name: string; protocol: string; server: string; port: number;
  username: string; password: string; network: string; path: string; host: string; tls: boolean; sni: string;
}

interface NodeEditorDialogProps {
  open: boolean;
  node?: Node;
  onOpenChange: (open: boolean) => void;
  onSave: (input: NodeEditorInput) => Promise<void>;
}

export function NodeEditorDialog({ open, node, onOpenChange, onSave }: NodeEditorDialogProps) {
  const [name,setName]=useState(""); const [protocol,setProtocol]=useState("socks5");
  const [server,setServer]=useState(""); const [port,setPort]=useState("1080");
  const [username,setUsername]=useState(""); const [password,setPassword]=useState("");
  const [network,setNetwork]=useState("tcp"); const [path,setPath]=useState(""); const [host,setHost]=useState("");
  const [tls,setTLS]=useState(false); const [sni,setSNI]=useState("");
  const [saving,setSaving]=useState(false); const [error,setError]=useState<string|null>(null);

  useEffect(()=>{
    if(!open)return;
    setName(node?.name??"");setProtocol(node?.protocol??"socks5");setServer(node?.server??"");setPort(String(node?.port??1080));
    setUsername("");setPassword("");setNetwork(node?.transport?.network||"tcp");setPath(node?.transport?.path||"");setHost(node?.transport?.host||"");
    setTLS(node?.tls?.enabled??false);setSNI(node?.tls?.sni||"");setError(null);
  },[open,node]);

  const submit=async(event:React.FormEvent<HTMLFormElement>)=>{
    event.preventDefault();const parsedPort=Number(port);
    if(!name.trim()||!server.trim()||!Number.isInteger(parsedPort)||parsedPort<1||parsedPort>65535)return;
    setSaving(true);
    try{await onSave({id:node?.id,name:name.trim(),protocol,server:server.trim(),port:parsedPort,username,password,network,path,host,tls,sni});onOpenChange(false)}
    catch(cause){setError(cause instanceof Error?cause.message:String(cause))}
    finally{setSaving(false)}
  };

  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="dialog-content" showCloseButton={false}>
    <div className="dialog-heading"><div><DialogTitle>{node?"Edit Base Node":"Add Base Node"}</DialogTitle><DialogDescription>{node?"Edit node details. Existing credentials remain protected in the OS credential vault.":"Credentials are stored in the operating system credential vault."}</DialogDescription></div><DialogClose render={<Button variant="ghost" size="icon" aria-label="Close" />}><X size={17}/></DialogClose></div>
    <form onSubmit={submit}>
      <label className="form-label">Name<Input value={name} onChange={e=>setName(e.target.value)} placeholder="Node name" autoFocus/></label>
      <label className="form-label">Protocol<Select value={protocol} onValueChange={v=>setProtocol(String(v))} disabled={!!node}><SelectTrigger className="native-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="socks5">SOCKS5</SelectItem><SelectItem value="http">HTTP</SelectItem></SelectContent></Select>{node&&<span className="form-hint">Protocol and stored credentials are preserved when editing.</span>}</label>
      <div className="form-grid"><label className="form-label">Server<Input value={server} onChange={e=>setServer(e.target.value)} placeholder="proxy.example.com"/></label><label className="form-label">Port<Input type="number" min={1} max={65535} value={port} onChange={e=>setPort(e.target.value)}/></label></div>
      {!node&&<div className="form-grid"><label className="form-label">Username (optional)<Input value={username} onChange={e=>setUsername(e.target.value)}/></label><label className="form-label">Password (optional)<Input type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label></div>}
      <div className="form-grid"><label className="form-label">Transport<Input value={network} onChange={e=>setNetwork(e.target.value)} placeholder="tcp / ws / grpc"/></label><label className="form-label">TLS SNI<Input value={sni} onChange={e=>setSNI(e.target.value)} placeholder="server name"/></label></div>
      <label className="setting-toggle"><span>TLS enabled</span><input type="checkbox" checked={tls} onChange={e=>setTLS(e.target.checked)}/></label>
      <div className="form-grid"><label className="form-label">Transport path<Input value={path} onChange={e=>setPath(e.target.value)} placeholder="/"/></label><label className="form-label">Transport host<Input value={host} onChange={e=>setHost(e.target.value)} placeholder="Host header"/></label></div>
      {!node&&<p className="form-hint">Manual node creation currently supports SOCKS5 and HTTP. Imported protocol credentials are never exposed in this editor.</p>}
      {error&&<div className="error-panel dialog-error">{error}</div>}
      <div className="dialog-actions"><Button type="button" variant="outline" onClick={()=>onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={saving||!name.trim()||!server.trim()}>{saving?"Saving…":node?"Save Changes":"Add Node"}</Button></div>
    </form>
  </DialogContent></Dialog>;
}
