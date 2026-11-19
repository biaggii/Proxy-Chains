import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (input: { name: string; url: string; userAgent: string; headers: Record<string,string>; updateMinutes: number }) => Promise<void>;
}

export function SubscriptionEditorDialog({ open, onOpenChange, onSave }: Props) {
  const [name,setName]=useState("");const [url,setURL]=useState("");const [userAgent,setUserAgent]=useState("");const [headerName,setHeaderName]=useState("");const [headerValue,setHeaderValue]=useState("");const [updateMinutes,setUpdateMinutes]=useState("60");const [saving,setSaving]=useState(false);const [error,setError]=useState<string|null>(null);
  const reset=()=>{setName("");setURL("");setUserAgent("");setHeaderName("");setHeaderValue("");setUpdateMinutes("60");setError(null)};
  const submit=async(event:React.FormEvent<HTMLFormElement>)=>{event.preventDefault();const interval=Number(updateMinutes);if(!name.trim()||!url.trim()||!Number.isInteger(interval)||interval<5)return;setSaving(true);try{await onSave({name:name.trim(),url:url.trim(),userAgent,headers:headerName.trim()?{[headerName.trim()]:headerValue}:{},updateMinutes:interval});reset();onOpenChange(false)}catch(cause){setError(cause instanceof Error?cause.message:String(cause))}finally{setSaving(false)}};
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="dialog-content" showCloseButton={false}><div className="dialog-heading"><div><DialogTitle>Add Subscription</DialogTitle><DialogDescription>Subscription URLs and header values are stored in the OS credential vault.</DialogDescription></div><DialogClose render={<Button variant="ghost" size="icon" aria-label="Close"/>}><X size={17}/></DialogClose></div><form onSubmit={submit}>
    <label className="form-label">Name<Input value={name} onChange={e=>setName(e.target.value)} placeholder="Subscription name" autoFocus/></label>
    <label className="form-label">Subscription URL<Input type="url" value={url} onChange={e=>setURL(e.target.value)} placeholder="https://example.com/subscription"/></label>
    <label className="form-label">User-Agent (optional)<Input value={userAgent} onChange={e=>setUserAgent(e.target.value)} placeholder="Default: v2rayN / ChainPort"/></label>
    <div className="form-grid"><label className="form-label">HTTP Header name<Input value={headerName} onChange={e=>setHeaderName(e.target.value)} placeholder="Authorization"/></label><label className="form-label">HTTP Header value<Input type="password" value={headerValue} onChange={e=>setHeaderValue(e.target.value)} placeholder="Optional"/></label></div>
    <label className="form-label">Refresh interval (minutes)<Input type="number" min={5} max={10080} value={updateMinutes} onChange={e=>setUpdateMinutes(e.target.value)}/></label>
    {error&&<div className="error-panel dialog-error">{error}</div>}
    <div className="dialog-actions"><Button type="button" variant="outline" onClick={()=>onOpenChange(false)}>Cancel</Button><Button type="submit" disabled={saving||!name.trim()||!url.trim()}>{saving?"Saving…":"Add Subscription"}</Button></div>
  </form></DialogContent></Dialog>;
}
