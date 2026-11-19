import { useEffect, useMemo, useState } from "react";
import { Events } from "@wailsio/runtime";
import { Activity, Check, CircleHelp, FileText, Layers3, Network, Pencil, Search, Settings2, Shield, ShieldCheck, SlidersHorizontal, Waypoints, Rss, Plus, Trash2, Edit3 } from "lucide-react";
import { WorkspaceService } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/service";
import { Protocol } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import type { Chain, Node, NodeGroup, Workspace } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ChainEditorDialog } from "@/components/chain-editor-dialog";
import { NodeEditorDialog, type NodeEditorInput } from "@/components/node-editor-dialog";
import { GroupManagerDialog } from "@/components/group-manager-dialog";
import { SubscriptionEditorDialog } from "@/components/subscription-editor-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [section, setSection] = useState("nodes");
  const [nodeView, setNodeView] = useState("base");
  const [selectedGroup,setSelectedGroup]=useState("all");
  const [filter, setFilter] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingChain, setEditingChain] = useState<Chain | undefined>();
  const [actionError, setActionError] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [nodeEditorOpen, setNodeEditorOpen] = useState(false);
  const [editingNode,setEditingNode]=useState<Node|undefined>();
  const [nodeEditorInitialGroupId,setNodeEditorInitialGroupId]=useState("");
  const [editingNodeCredentials,setEditingNodeCredentials]=useState<{username:string;password:string}>({username:"",password:""});
  const [groupManagerOpen,setGroupManagerOpen]=useState(false);
  const [subscriptionManagerOpen,setSubscriptionManagerOpen]=useState(false);
  const [nodeContext,setNodeContext]=useState<{node:Node;x:number;y:number}|null>(null);
  const [groupContext,setGroupContext]=useState<{group:NodeGroup;x:number;y:number}|null>(null);
  const [chainContext,setChainContext]=useState<{chain:Chain;x:number;y:number}|null>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<{ status: string; pid?: number; lastError?: string }>({ status: "stopped" });
  const [runtimeLogs, setRuntimeLogs] = useState<string[]>([]);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [subscriptionEditorOpen,setSubscriptionEditorOpen]=useState(false);
  const [subscriptionBusyID,setSubscriptionBusyID]=useState<string|null>(null);
  const [settingsDraft,setSettingsDraft]=useState<Workspace["settings"]|null>(null);
  const [settingsBusy,setSettingsBusy]=useState(false);

  useEffect(() => {
    WorkspaceService.GetWorkspace()
      .then(setWorkspace)
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : String(error)));
    WorkspaceService.GetRuntimeStatus().then(setRuntimeStatus).catch(() => undefined);
    WorkspaceService.GetRuntimeLogs().then((logs)=>setRuntimeLogs(logs??[])).catch(() => undefined);
    const off = Events.On("core:runtime", (event) => {
      const payload = event.data as { type?: string; message?: string; snapshot?: { status: string; pid?: number; lastError?: string } };
      if (payload.type === "log" && payload.message) setRuntimeLogs((current) => [...current.slice(-1999), payload.message!]);
      if (payload.snapshot) setRuntimeStatus(payload.snapshot);
    });
    return off;
  }, []);

  useEffect(()=>{if(workspace)setSettingsDraft(structuredClone(workspace.settings))},[workspace?.settings]);

  const nodes = workspace?.nodes ?? [];
  const chains = workspace?.chains ?? [];
  const subscriptions = workspace?.subscriptions ?? [];
  const nodeGroups=useMemo(()=>[
    {id:"all",label:"All",count:nodes.length},
    ...(nodes.some(node=>!node.sourceId&&!node.groupId)?[{id:"customs",label:"Customs",count:nodes.filter(node=>!node.sourceId&&!node.groupId).length}]:[]),
    ...(workspace?.groups??[]).map(group=>({id:group.id,label:group.name,count:nodes.filter(node=>node.groupId===group.id).length})),
    ...subscriptions.map(subscription=>({id:subscription.id,label:subscription.name,count:nodes.filter(node=>node.sourceId===subscription.id).length})),
  ],[nodes,subscriptions,workspace?.groups]);
  const visibleNodes = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase();
    return nodes.filter(node=>{
      const matchesGroup=selectedGroup==="all"||(selectedGroup==="customs"?!node.sourceId&&!node.groupId:node.groupId===selectedGroup||node.sourceId===selectedGroup);
      const matchesQuery=!query||[node.name,node.server,node.protocol].some(value=>value.toLocaleLowerCase().includes(query));
      return matchesGroup&&matchesQuery;
    });
  }, [filter, nodes, selectedGroup]);

  useEffect(()=>{if(!nodeGroups.some(group=>group.id===selectedGroup))setSelectedGroup("all")},[nodeGroups,selectedGroup]);

  const tunLabel = useMemo(() => {
    if (!workspace || workspace.tun.kind === "none") return "Not bound";
    if (workspace.tun.kind === "node") return nodes.find((node) => node.id === workspace.tun.targetId)?.name ?? "Missing node";
    return chains.find((chain) => chain.id === workspace.tun.targetId)?.name ?? "Missing chain";
  }, [chains, nodes, workspace]);

  const saveChain = async (input: { id?: string; name: string; hopNodeIds: string[]; listenPort: number }) => {
    try {
      const next = input.id
        ? await WorkspaceService.UpdateChain({ id: input.id, name: input.name, hopNodeIds: input.hopNodeIds, listenPort: input.listenPort })
        : await WorkspaceService.CreateChain({ name: input.name, hopNodeIds: input.hopNodeIds, listenPort: input.listenPort });
      setWorkspace(next);
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
      throw error;
    }
  };

  const editChain = (chain: Chain) => { setEditingChain(chain); setEditorOpen(true); };

  const bindChainTUN = async (chainID: string) => {
    try { setWorkspace(await WorkspaceService.BindTUNToChain(chainID)); setActionError(null); }
    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
  };

  const bindNodeTUN = async (nodeID: string) => {
    try { setWorkspace(await WorkspaceService.BindTUNToBaseNode(nodeID)); setActionError(null); }
    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
  };

  const deleteNode=async(nodeID:string)=>{
    if(!window.confirm("Delete this Base Node? Nodes used by a Chain cannot be deleted."))return;
    try{setWorkspace(await WorkspaceService.DeleteNode(nodeID));setActionError(null)}catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const deleteChain=async(chainID:string)=>{
    if(!window.confirm("Delete this Chain and its local port mapping?"))return;
    try{setWorkspace(await WorkspaceService.DeleteChain(chainID));setActionError(null)}catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const setActiveNode = async (nodeID: string) => {
    try { setWorkspace(await WorkspaceService.SetActiveBaseNode(nodeID)); setActionError(null); }
    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
  };

  const toggleTUN = async () => {
    if (!workspace) return;
    try { setWorkspace(await WorkspaceService.SetTUNEnabled(!workspace.tun.enabled)); setActionError(null); }
    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
  };

  const importLegacyState = async () => {
    try {
      const report = await WorkspaceService.ImportLegacyStateFile();
      const next = await WorkspaceService.GetWorkspace();
      setWorkspace(next);
      setImportMessage(`Imported ${report.nodes} nodes, ${report.chains} chains and ${report.subscriptions} subscriptions. Moved ${report.secretsMoved} secrets to the OS credential vault.${report.warnings?.length ? ` ${report.warnings.join(" ")}` : ""}`);
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  };

  const saveNode = async (input: NodeEditorInput) => {
    try {
      const next = input.id
        ? await WorkspaceService.UpdateNode({id:input.id,name:input.name,server:input.server,port:input.port,network:input.network,path:input.path,host:input.host,tls:input.tls,sni:input.sni,insecure:input.insecure,alpn:input.alpn,protocol:input.protocol?(input.protocol==="socks5"?Protocol.ProtocolSOCKS5:Protocol.ProtocolHTTP):undefined,username:input.protocol?input.username:null,password:input.protocol?input.password:null,groupId:input.groupId})
        : await WorkspaceService.CreateNode({name:input.name,protocol:input.protocol === "socks5" ? Protocol.ProtocolSOCKS5 : Protocol.ProtocolHTTP,server:input.server,port:input.port,username:input.username,password:input.password,uuid:"",tls:input.tls,sni:input.sni,insecure:input.insecure,alpn:input.alpn,network:input.network,path:input.path,host:input.host,groupId:input.groupId});
      setWorkspace(next);
      setActionError(null);
      setEditingNode(undefined);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
      throw error;
    }
  };

  const openNodeEditor=async(node?:Node, groupId?:string)=>{
    setNodeContext(null);setGroupContext(null);setEditingNode(node);setNodeEditorInitialGroupId(groupId??"");setEditingNodeCredentials({username:"",password:""});
    if(node&&(node.protocol==="socks5"||node.protocol==="http")){
      try{const credentials=await WorkspaceService.GetNodeCredentials(node.id);setEditingNodeCredentials({username:credentials.username??"",password:credentials.password??""})}
      catch(error){setActionError(error instanceof Error?error.message:String(error));return}
    }
    setNodeEditorOpen(true);
  };

  const createNodeGroup=async(name:string)=>{const next=await WorkspaceService.CreateNodeGroup(name);setWorkspace(next);const createdGroup=next.groups?.[next.groups.length-1];setSelectedGroup(createdGroup?.id??"all");setActionError(null)};
  const renameNodeGroup=async(id:string,name:string)=>{setWorkspace(await WorkspaceService.RenameNodeGroup(id,name));setActionError(null)};
  const deleteNodeGroup=async(id:string)=>{setWorkspace(await WorkspaceService.DeleteNodeGroup(id));if(selectedGroup===id)setSelectedGroup("all");setActionError(null)};

  const renameGroupFromContext=async(group:NodeGroup)=>{
    setGroupContext(null);
    const name=window.prompt("Rename node group",group.name);
    if(name===null||!name.trim())return;
    try{await renameNodeGroup(group.id,name.trim())}catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const removeGroupFromContext=async(group:NodeGroup)=>{
    setGroupContext(null);
    if(!window.confirm(`Delete group "${group.name}"? Nodes will remain and become ungrouped.`))return;
    try{await deleteNodeGroup(group.id)}catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const createSubscription=async(input:{name:string;url:string;userAgent:string;headers:Record<string,string>;updateMinutes:number})=>{
    try{setWorkspace(await WorkspaceService.CreateSubscription(input));setActionError(null)}catch(error){setActionError(error instanceof Error?error.message:String(error));throw error}
  };

  const refreshSubscription=async(id:string)=>{
    setSubscriptionBusyID(id);try{setWorkspace(await WorkspaceService.RefreshSubscription(id));setActionError(null)}catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setSubscriptionBusyID(null)}
  };

  const deleteSubscription=async(id:string)=>{
    if(!window.confirm("Delete this subscription and all nodes imported from it?"))return;
    try{setWorkspace(await WorkspaceService.DeleteSubscription(id));setActionError(null)}catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const saveSettings=async()=>{
    if(!settingsDraft)return;setSettingsBusy(true);
    try{const next=await WorkspaceService.UpdateSettings(settingsDraft);setWorkspace(next);setActionError(null)}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setSettingsBusy(false)}
  };

  const browseCoreExecutable=async()=>{
    if(!settingsDraft)return;
    try{const coreName=settingsDraft.core.type.toLowerCase();const selectedPath=await WorkspaceService.PickCoreExecutable(coreName);if(!selectedPath)return;setSettingsDraft(current=>current?{...current,core:{...current.core,executables:{...(current.core.executables??{}),[coreName]:selectedPath}}}:current);setActionError(null)}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const toggleCore = async () => {
    setRuntimeBusy(true);
    try {
      if (runtimeStatus.status === "running" || runtimeStatus.status === "starting") await WorkspaceService.StopCore();
      else await WorkspaceService.StartCore();
      setActionError(null);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setRuntimeBusy(false);
      WorkspaceService.GetRuntimeStatus().then(setRuntimeStatus).catch(() => undefined);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-icon"><Waypoints size={21} /></div>
          <div><div className="brand-name">ChainPort</div><div className="brand-caption">GATEWAY</div></div>
        </div>
        <div className="toolbar-status"><span className={`status-dot ${runtimeStatus.status === "running" ? "status-running" : runtimeStatus.status === "failed" ? "status-failed" : ""}`} /> {runtimeStatus.status === "running" ? `Running · PID ${runtimeStatus.pid ?? "—"}` : runtimeStatus.status === "failed" ? "Core failed" : runtimeStatus.status === "stopping" ? "Stopping" : "Stopped"}</div>
        <div className="toolbar-actions">
          <Button variant="outline" size="sm" onClick={() => { setLogsOpen(true); WorkspaceService.GetRuntimeLogs().then((logs)=>setRuntimeLogs(logs??[])).catch(() => undefined); }}><FileText size={15} /> Logs</Button>
          <div className="tun-summary"><Shield size={15} /> <span>TUN: {tunLabel}</span></div>
          <Button variant={workspace?.tun.enabled ? "default" : "outline"} size="sm" disabled={!workspace || workspace.tun.kind === "none"} onClick={() => void toggleTUN()} title="Enable or disable native TUN routing on the next core start">TUN CONFIG {workspace?.tun.enabled ? "ON" : "OFF"}</Button>
          <Button size="sm" disabled={runtimeBusy || runtimeStatus.status === "stopping"} onClick={() => void toggleCore()}>{runtimeBusy ? "Please wait…" : runtimeStatus.status === "running" ? "Stop" : "Start"}</Button>
        </div>
      </header>

      <div className="workspace-layout">
        <aside className="sidebar">
          <button className={`nav-item ${section === "nodes" ? "active" : ""}`} aria-label="Node Groups" title="Node Groups" onClick={() => setSection("nodes")}><Network size={18} /></button>
          <button className={`nav-item ${section === "settings" ? "active" : ""}`} aria-label="Settings" title="Settings" onClick={() => setSection("settings")}><Settings2 size={18} /></button>
          <div className="sidebar-footer"><div className="sidebar-footer-icon" title="ChainPort Gateway · Go · Wails v3"><CircleHelp size={16} /></div></div>
        </aside>

        <section className="main-content">
          {section === "nodes" ? (
            <>
              <div className="page-heading"><div><div className="eyebrow">ROUTING WORKSPACE</div><h1>Node Groups</h1><p>Manage imported proxy nodes and reusable multi-hop chains.</p></div><div className="heading-metrics"><span><strong>{nodes.length}</strong> Base Nodes</span><span><strong>{chains.length}</strong> Chains</span></div></div>
              <Tabs value={nodeView} onValueChange={(value) => setNodeView(String(value))} className="node-tabs">
                <TabsList className="tabs-list"><TabsTrigger value="base" className="tab-trigger"><Network size={15} /> Base</TabsTrigger><TabsTrigger value="chain" className="tab-trigger"><Layers3 size={15} /> Chain</TabsTrigger></TabsList>
                <TabsContent value="base" className="tab-panel">
                  <div className="panel-heading"><div><h2>Base Nodes</h2><p>Single-hop endpoints from manual entries and subscription sources.</p></div><div className="panel-tools"><div className="search-wrap"><Search size={15} /><Input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter by name, address or protocol" /></div>{nodes.length===0&&subscriptions.length===0&&<Button variant="outline" onClick={()=>void importLegacyState()}>Import Legacy State</Button>}<Button variant="outline" onClick={()=>setSubscriptionManagerOpen(true)}><Rss size={14}/> Subscriptions…</Button><Button onClick={() => openNodeEditor()}>Add Node</Button></div></div>
                  <div className="node-group-bar" role="tablist" aria-label="Node groups"><div className="node-group-chips">{nodeGroups.map(group=><button key={group.id} className={`group-chip ${selectedGroup===group.id?"active":""}`} onClick={()=>setSelectedGroup(group.id)} onContextMenu={event=>{const customGroup=(workspace?.groups??[]).find(item=>item.id===group.id);if(!customGroup)return;event.preventDefault();setGroupContext({group:customGroup,x:Math.min(event.clientX,window.innerWidth-220),y:Math.min(event.clientY,window.innerHeight-180)})}} role="tab" aria-selected={selectedGroup===group.id}>{group.label}<span>{group.count}</span></button>)}</div><Button size="sm" variant="outline" onClick={()=>setGroupManagerOpen(true)}><Plus size={14}/> Create Group</Button></div>
                  {loadError ? <div className="error-panel">Could not load workspace: {loadError}</div> : <Card className="table-card"><CardContent className="table-content"><Table className="data-table"><TableHeader><TableRow><TableHead>TYPE</TableHead><TableHead>REMARKS</TableHead><TableHead>ADDRESS</TableHead><TableHead>PORT</TableHead><TableHead>TRANSPORT</TableHead><TableHead>TLS</TableHead><TableHead>GROUP / SOURCE</TableHead><TableHead>ACTIVE</TableHead><TableHead>ACTIONS</TableHead></TableRow></TableHeader><TableBody>{visibleNodes.map(node=>{const source=subscriptions.find(item=>item.id===node.sourceId);const group=(workspace?.groups??[]).find(item=>item.id===node.groupId);const groupLabel=[group?.name,source?.name??(node.sourceId?"Unknown source":null)].filter(Boolean).join(" · ")||"Custom";return <TableRow key={node.id} data-active={workspace?.activeNodeId===node.id} onClick={()=>void setActiveNode(node.id)} onDoubleClick={()=>void openNodeEditor(node)} onContextMenu={event=>{event.preventDefault();setNodeContext({node,x:Math.min(event.clientX,window.innerWidth-220),y:Math.min(event.clientY,window.innerHeight-230)})}} className="node-data-row"><TableCell><span className="protocol-pill">{node.protocol}</span></TableCell><TableCell className="cell-strong">{node.name}</TableCell><TableCell className="mono">{node.server}</TableCell><TableCell className="mono">{node.port}</TableCell><TableCell>{node.transport?.network||"tcp"}</TableCell><TableCell>{node.tls?.enabled?"TLS":"—"}</TableCell><TableCell>{groupLabel}</TableCell><TableCell>{workspace?.activeNodeId===node.id?<span className="active-node-pill"><Check size={12}/> Active</span>:"—"}</TableCell><TableCell><div className="row-actions"><Button size="icon-sm" variant="ghost" title="Edit node" aria-label={`Edit ${node.name}`} onClick={event=>{event.stopPropagation();void openNodeEditor(node)}}><Pencil size={14}/></Button><Button size="icon-sm" variant="ghost" title="Delete node" aria-label={`Delete ${node.name}`} className="node-delete-action" onClick={event=>{event.stopPropagation();void deleteNode(node.id)}}><Trash2 size={14}/></Button></div></TableCell></TableRow>})}</TableBody></Table>{visibleNodes.length===0&&<div className="empty-state"><div className="empty-icon"><Network size={22}/></div><strong>{filter?"No matching nodes":selectedGroup==="all"?"No Base Nodes yet":"This group has no nodes"}</strong><span>{filter?"Try a different search term.":"Add a node or import a subscription to get started."}</span></div>}</CardContent></Card>}
                </TabsContent>
                <TabsContent value="chain" className="tab-panel">
                  <div className="panel-heading"><div><h2>Chain Nodes</h2><p>Compose ordered routes. Each saved Chain owns one local listener.</p></div><Button onClick={() => { setEditingChain(undefined); setEditorOpen(true); }} disabled={nodes.length === 0}>Create Chain</Button></div>
                  <Card className="table-card"><CardContent className="table-content"><Table className="data-table"><TableHeader><TableRow><TableHead>NAME</TableHead><TableHead>ROUTE · ENTRY → EXIT</TableHead><TableHead>LOCAL PORT</TableHead><TableHead>HOPS</TableHead><TableHead>TUN</TableHead><TableHead>ACTIONS</TableHead></TableRow></TableHeader><TableBody>{chains.map((chain) => { const hopIDs = chain.hopNodeIds ?? []; const port = (workspace?.portBindings ?? []).find((binding) => binding.chainId === chain.id)?.listenPort; return <TableRow key={chain.id} onDoubleClick={()=>editChain(chain)} onContextMenu={event=>{event.preventDefault();setChainContext({chain,x:Math.min(event.clientX,window.innerWidth-220),y:Math.min(event.clientY,window.innerHeight-190)})}} className="node-data-row"><TableCell className="cell-strong">{chain.name}</TableCell><TableCell>{hopIDs.map((id) => nodes.find((node) => node.id === id)?.name ?? "Missing node").join(" → ")}</TableCell><TableCell className="mono">{port ?? "—"}</TableCell><TableCell>{hopIDs.length}</TableCell><TableCell>{workspace?.tun.kind === "chain" && workspace.tun.targetId === chain.id ? <span className="bound-pill">BOUND</span> : "—"}</TableCell><TableCell><div className="row-actions"><Button variant="ghost" size="sm" onClick={() => editChain(chain)} title="Edit Chain"><Pencil size={14} /></Button><Button variant="outline" size="sm" onClick={() => void bindChainTUN(chain.id)} title="Set this complete Chain as the TUN route target"><ShieldCheck size={13} /> Bind TUN</Button><Button variant="ghost" size="sm" onClick={()=>void deleteChain(chain.id)}>Delete</Button></div></TableCell></TableRow>; })}</TableBody></Table>{chains.length === 0 && <div className="empty-state"><div className="empty-icon"><Layers3 size={22} /></div><strong>No Chains created</strong><span>Create a Chain to combine Base Nodes into an ordered route.</span></div>}</CardContent></Card>
                </TabsContent>
              </Tabs>
            </>
          ) : (
            <>
              <div className="page-heading settings-page-heading"><div><div className="eyebrow">APPLICATION</div><h1>Settings</h1><p>Configure the proxy core and network behavior.</p></div><Button onClick={()=>void saveSettings()} disabled={settingsBusy}>{settingsBusy?"Saving…":"Save Settings"}</Button></div>
              {settingsDraft&&<>
                <div className="settings-grid">
                  <Card><CardHeader><CardTitle><SlidersHorizontal size={17}/> Core Engine</CardTitle></CardHeader><CardContent>
                    <label className="form-label">Selected core<Select value={settingsDraft.core.type} onValueChange={value=>setSettingsDraft({...settingsDraft,core:{...settingsDraft.core,type:String(value)}})}><SelectTrigger className="native-select"><SelectValue placeholder="Select core"/></SelectTrigger><SelectContent><SelectItem value="sing-box">sing-box</SelectItem><SelectItem value="xray">Xray</SelectItem><SelectItem value="mihomo">Mihomo</SelectItem></SelectContent></Select></label>
                    <label className="form-label">Core executable path<div className="core-path-control"><Input value={(settingsDraft.core.executables??{})[settingsDraft.core.type.toLowerCase()]??""} onChange={e=>setSettingsDraft({...settingsDraft,core:{...settingsDraft.core,executables:{...(settingsDraft.core.executables??{}),[settingsDraft.core.type.toLowerCase()]:e.target.value}}})} placeholder="/usr/bin/sing-box"/><Button type="button" variant="outline" onClick={()=>void browseCoreExecutable()} disabled={settingsBusy}>Browse…</Button></div></label>
                    <label className="form-label">Log level<Select value={settingsDraft.core.logLevel} onValueChange={value=>setSettingsDraft({...settingsDraft,core:{...settingsDraft.core,logLevel:String(value)}})}><SelectTrigger className="native-select"><SelectValue placeholder="Select log level"/></SelectTrigger><SelectContent><SelectItem value="trace">trace</SelectItem><SelectItem value="debug">debug</SelectItem><SelectItem value="info">info</SelectItem><SelectItem value="warning">warning</SelectItem><SelectItem value="error">error</SelectItem></SelectContent></Select></label>
                  </CardContent></Card>
                  <Card><CardHeader><CardTitle><Activity size={17}/> Shared Listener</CardTitle></CardHeader><CardContent>
                    <label className="form-label">Listen host<Input value={settingsDraft.baseListenHost} onChange={e=>setSettingsDraft({...settingsDraft,baseListenHost:e.target.value})}/></label>
                    <label className="form-label">Base port<Input type="number" min={1} max={65535} value={settingsDraft.baseListenPort} onChange={e=>setSettingsDraft({...settingsDraft,baseListenPort:Number(e.target.value)})}/></label>
                    <label className="form-label">Remote DNS (HTTPS)<Input value={settingsDraft.network.remoteDNSUrl} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,remoteDNSUrl:e.target.value}})}/></label>
                    <label className="form-label">Bootstrap DNS<Input value={settingsDraft.network.bootstrapDNS} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,bootstrapDNS:e.target.value}})}/></label>
                  </CardContent></Card>
                  <Card><CardHeader><CardTitle><Shield size={17}/> Network Features</CardTitle></CardHeader><CardContent>
                    {([ ["enableUDP","UDP forwarding"],["enableIPv6","IPv6"],["enableSniffing","Protocol sniffing"],["allowLAN","Allow LAN"],["enableMux","Multiplexing"],["allowInsecure","Allow insecure TLS"],["enableFragment","TLS fragmentation"],["enableFinalFragment","Final outbound fragmentation"],["blockQUIC","Block QUIC"] ] as const).map(([key,label])=><label className="setting-toggle" key={key}><span>{label}</span><input type="checkbox" checked={settingsDraft.network[key]} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,[key]:e.target.checked}})}/></label>)}
                    <label className="form-label">sing-box mux protocol<Select value={settingsDraft.network.singboxMuxProtocol||"h2mux"} onValueChange={value=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,singboxMuxProtocol:String(value)}})}><SelectTrigger className="native-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="h2mux">h2mux</SelectItem><SelectItem value="smux">smux</SelectItem><SelectItem value="yamux">yamux</SelectItem></SelectContent></Select></label>
                    <label className="form-label">Xray fragment packet mode<Select value={settingsDraft.network.xrayFragmentPackets||"tlshello"} onValueChange={value=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentPackets:String(value)}})}><SelectTrigger className="native-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="tlshello">TLS Hello</SelectItem><SelectItem value="1-3">First 1–3 packets</SelectItem></SelectContent></Select></label>
                    <label className="form-label">Xray fragment lengths<Input value={(settingsDraft.network.xrayFragmentLengths??[]).join(",")} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentLengths:e.target.value.split(",").map(value=>value.trim()).filter(Boolean)}})} placeholder="50-100"/></label>
                    <label className="form-label">Xray fragment delays (ms)<Input value={(settingsDraft.network.xrayFragmentDelays??[]).join(",")} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentDelays:e.target.value.split(",").map(value=>value.trim()).filter(Boolean)}})} placeholder="10-20"/></label>
                    <label className="form-label">Xray max split (optional)<Input type="number" min={0} max={64} value={settingsDraft.network.xrayFragmentMaxSplit??0} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentMaxSplit:Number(e.target.value)}})}/></label>
                  </CardContent></Card>
                  <Card><CardHeader><CardTitle><Settings2 size={17}/> Application</CardTitle></CardHeader><CardContent>
                    {([ ["autoStart","Start core on application launch"],["runOnStartup","Run application on system startup"],["minimizeOnStart","Start minimized"],["closeToTray","Close to system tray"] ] as const).map(([key,label])=><label className="setting-toggle" key={key}><span>{label}</span><input type="checkbox" checked={settingsDraft[key]} onChange={e=>setSettingsDraft({...settingsDraft,[key]:e.target.checked})}/></label>)}
                    <p className="setting-note">Run on startup updates the per-user OS launch registration. Start-on-launch, minimize and tray behavior take effect the next time the application starts.</p>
                  </CardContent></Card>
                </div>
              </>}
            </>
          )}
          {actionError && <div className="error-panel action-error">{actionError}</div>}
          {importMessage && <div className="import-success">{importMessage}</div>}
          <footer className="content-footer"><span>ChainPort Gateway · Rewrite Preview</span><span>Schema v{workspace?.schemaVersion ?? 1}</span></footer>
        </section>
      </div>
      {nodeContext&&<div className="context-menu-backdrop" onClick={()=>setNodeContext(null)} onContextMenu={event=>{event.preventDefault();setNodeContext(null)}}><div className="node-context-menu" style={{left:nodeContext.x,top:nodeContext.y}} onClick={event=>event.stopPropagation()}>
        <div className="context-menu-title">{nodeContext.node.name}</div>
        <button onClick={()=>{void setActiveNode(nodeContext.node.id);setNodeContext(null)}}><Check size={14}/> Use as active node</button>
        <button onClick={()=>{void bindNodeTUN(nodeContext.node.id);setNodeContext(null)}}><ShieldCheck size={14}/> Bind TUN to this node</button>
        <div className="context-menu-separator"/>
        <button onClick={()=>{void openNodeEditor(nodeContext.node);setNodeContext(null)}}><Edit3 size={14}/> Edit</button>
        <button className="context-menu-danger" onClick={()=>{const id=nodeContext.node.id;setNodeContext(null);void deleteNode(id)}}><Trash2 size={14}/> Delete</button>
        <div className="context-menu-separator"/>
        <button onClick={()=>{setNodeContext(null);openNodeEditor()}}><Plus size={14}/> Create node</button>
      </div></div>}
      {groupContext&&<div className="context-menu-backdrop" onClick={()=>setGroupContext(null)} onContextMenu={event=>{event.preventDefault();setGroupContext(null)}}><div className="node-context-menu" style={{left:groupContext.x,top:groupContext.y}} onClick={event=>event.stopPropagation()}>
        <div className="context-menu-title">{groupContext.group.name}</div>
        <button onClick={()=>{const group=groupContext.group;setGroupContext(null);void openNodeEditor(undefined,group.id)}}><Plus size={14}/> Add Node to Group</button>
        <button onClick={()=>void renameGroupFromContext(groupContext.group)}><Edit3 size={14}/> Rename Group</button>
        <div className="context-menu-separator"/>
        <button className="context-menu-danger" onClick={()=>void removeGroupFromContext(groupContext.group)}><Trash2 size={14}/> Delete Group</button>
      </div></div>}
      {chainContext&&<div className="context-menu-backdrop" onClick={()=>setChainContext(null)} onContextMenu={event=>{event.preventDefault();setChainContext(null)}}><div className="node-context-menu" style={{left:chainContext.x,top:chainContext.y}} onClick={event=>event.stopPropagation()}>
        <div className="context-menu-title">{chainContext.chain.name}</div>
        <button onClick={()=>{editChain(chainContext.chain);setChainContext(null)}}><Edit3 size={14}/> Edit Chain</button>
        <button onClick={()=>{void bindChainTUN(chainContext.chain.id);setChainContext(null)}}><ShieldCheck size={14}/> Bind TUN to this Chain</button>
        <div className="context-menu-separator"/>
        <button className="context-menu-danger" onClick={()=>void deleteChain(chainContext.chain.id).finally(()=>setChainContext(null))}><Trash2 size={14}/> Remove Chain</button>
        <button onClick={()=>{setEditingChain(undefined);setEditorOpen(true);setChainContext(null)}}><Plus size={14}/> Create Chain</button>
      </div></div>}
      <ChainEditorDialog open={editorOpen} nodes={nodes} chain={editingChain} listenPort={editingChain ? (workspace?.portBindings ?? []).find((binding) => binding.chainId === editingChain.id)?.listenPort : undefined} onOpenChange={setEditorOpen} onSave={saveChain} />
      <NodeEditorDialog open={nodeEditorOpen} node={editingNode} groups={workspace?.groups??[]} credentials={editingNodeCredentials} initialGroupId={nodeEditorInitialGroupId} onOpenChange={open=>{setNodeEditorOpen(open);if(!open){setEditingNode(undefined);setNodeEditorInitialGroupId("");setEditingNodeCredentials({username:"",password:""})}}} onSave={saveNode} />
      <GroupManagerDialog open={groupManagerOpen} groups={workspace?.groups??[]} onOpenChange={setGroupManagerOpen} onCreate={createNodeGroup} onRename={renameNodeGroup} onDelete={deleteNodeGroup}/>
      <SubscriptionEditorDialog open={subscriptionEditorOpen} onOpenChange={open=>{setSubscriptionEditorOpen(open);if(!open)setSubscriptionManagerOpen(true)}} onSave={createSubscription}/>
      <Dialog open={subscriptionManagerOpen} onOpenChange={setSubscriptionManagerOpen}>
        <DialogContent className="subscription-manager-dialog" showCloseButton>
          <div className="dialog-heading"><div><DialogTitle>Subscription Groups</DialogTitle><DialogDescription>Manage feeds and the Base Nodes imported into each group. Feed URLs and headers remain in the OS credential vault.</DialogDescription></div></div>
          <div className="subscription-manager-toolbar"><span>{subscriptions.length} feed(s) · {nodes.filter(node=>node.sourceId).length} imported nodes</span><div className="row-actions"><Button size="sm" variant="outline" disabled={!subscriptions.length||subscriptionBusyID!==null} onClick={()=>void WorkspaceService.RefreshAllSubscriptions().then(([next,failures])=>{setWorkspace(next);setActionError(failures?.length?failures.join("; "):null)}).catch(error=>setActionError(error instanceof Error?error.message:String(error)))}>Refresh All</Button><Button size="sm" onClick={()=>{setSubscriptionManagerOpen(false);setSubscriptionEditorOpen(true)}}><Plus size={14}/> Add Subscription</Button></div></div>
          <Card className="table-card"><CardContent className="table-content"><Table className="data-table"><TableHeader><TableRow><TableHead>GROUP</TableHead><TableHead>FORMAT</TableHead><TableHead>NODES</TableHead><TableHead>INTERVAL</TableHead><TableHead>LAST UPDATED</TableHead><TableHead>STATUS</TableHead><TableHead>ACTIONS</TableHead></TableRow></TableHeader><TableBody>{subscriptions.map(subscription=><TableRow key={subscription.id}><TableCell className="cell-strong">{subscription.name}</TableCell><TableCell><span className="protocol-pill">{subscription.format}</span></TableCell><TableCell>{nodes.filter(node=>node.sourceId===subscription.id).length}</TableCell><TableCell>{subscription.updateMinutes} min</TableCell><TableCell className="mono">{subscription.lastUpdated?new Date(subscription.lastUpdated).toLocaleString():"Never"}</TableCell><TableCell>{subscription.lastError?<span className="error-status">Error</span>:subscription.enabled?<span className="muted-status">Ready</span>:<span className="muted-status">Paused</span>}</TableCell><TableCell><div className="row-actions"><Button size="sm" variant="outline" disabled={subscriptionBusyID!==null} onClick={()=>void refreshSubscription(subscription.id)}>{subscriptionBusyID===subscription.id?"Updating…":"Update"}</Button><Button size="sm" variant="ghost" disabled={subscriptionBusyID!==null} onClick={()=>void WorkspaceService.SetSubscriptionEnabled(subscription.id,!subscription.enabled).then(setWorkspace).catch(error=>setActionError(error instanceof Error?error.message:String(error)))}>{subscription.enabled?"Pause":"Resume"}</Button><Button size="sm" variant="ghost" onClick={()=>void deleteSubscription(subscription.id)}>Delete</Button></div></TableCell></TableRow>)}</TableBody></Table>{subscriptions.length===0&&<div className="empty-state"><div className="empty-icon"><Rss size={22}/></div><strong>No subscription groups</strong><span>Add a subscription to import Base Nodes into a group.</span></div>}</CardContent></Card>
          {subscriptions.some(subscription=>subscription.lastError)&&<div className="error-panel action-error">{subscriptions.filter(subscription=>subscription.lastError).map(subscription=>`${subscription.name}: ${subscription.lastError}`).join(" · ")}</div>}
        </DialogContent>
      </Dialog>
      <Dialog open={logsOpen} onOpenChange={setLogsOpen}>
        <DialogContent className="logs-dialog" showCloseButton>
            <div className="dialog-heading"><div><DialogTitle>Core Runtime Logs</DialogTitle><DialogDescription>Application diagnostics, config validation and live core stdout/stderr. Secret values are redacted.</DialogDescription></div></div>
          <div className="runtime-log-view" role="log" aria-live="polite">{runtimeLogs.length ? runtimeLogs.map((line, index) => <div className="runtime-log-line" key={`${index}-${line}`}>{line}</div>) : <div className="runtime-log-empty">No runtime output yet. Start the selected core to see logs.</div>}</div>
          <div className="dialog-actions"><Button variant="outline" onClick={() => {WorkspaceService.ClearRuntimeLogs();setRuntimeLogs([])}}>Clear</Button><Button onClick={() => WorkspaceService.GetRuntimeLogs().then((logs)=>setRuntimeLogs(logs??[]))}>Refresh</Button></div>
        </DialogContent>
      </Dialog>
    </main>
  );
}

export default App;
