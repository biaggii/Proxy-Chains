import { useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import { Events } from "@wailsio/runtime";
import { Activity, ArrowDown, ArrowUp, ArrowUpDown, Check, CircleHelp, Copy, FileText, FolderInput, Layers3, Network, Pencil, Search, Settings2, Shield, ShieldCheck, SlidersHorizontal, Waypoints, Rss, Plus, Trash2, Edit3, Database, FolderOpen, Download, Upload, KeyRound } from "lucide-react";
import { WorkspaceService } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/service";
import { Protocol } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import type { Chain, Node, Workspace } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/domain";
import type { State as ProfileState } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/profiles";
import type { NodeTestResult } from "../bindings/github.com/biaggii/Proxy-Chains/go-wails3/internal/service";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ChainEditorDialog } from "@/components/chain-editor-dialog";
import { NodeEditorDialog, type NodeEditorInput } from "@/components/node-editor-dialog";
import { GroupManagerDialog } from "@/components/group-manager-dialog";
import { NodeGroupTransferDialog } from "@/components/node-group-transfer-dialog";
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
  const [contextMenu,setContextMenu]=useState<
    | {kind:"node";node:Node;nodeIDs:string[];x:number;y:number}
    | {kind:"group";group:{kind:"all"|"custom"|"subscription"|"customs";id:string;name:string};x:number;y:number}
    | {kind:"chain";chain:Chain;x:number;y:number}
    | null
  >(null);
  const [nodeTransfer,setNodeTransfer]=useState<{node:Node;mode:"move"|"copy"}|null>(null);
  const contextMenuRef=useRef<HTMLDivElement>(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<{ status: string; pid?: number; lastError?: string }>({ status: "stopped" });
  const [runtimeLogs, setRuntimeLogs] = useState<string[]>([]);
  const [runtimeBusy, setRuntimeBusy] = useState(false);
  const [subscriptionEditorOpen,setSubscriptionEditorOpen]=useState(false);
  const [subscriptionBusyID,setSubscriptionBusyID]=useState<string|null>(null);
  const [settingsDraft,setSettingsDraft]=useState<Workspace["settings"]|null>(null);
  const [settingsBusy,setSettingsBusy]=useState(false);
  const [profileState,setProfileState]=useState<ProfileState|null>(null);
  const [selectedProfileID,setSelectedProfileID]=useState("");
  const [profileBusy,setProfileBusy]=useState(false);
  const [profileDialogMode,setProfileDialogMode]=useState<"create"|"rename"|null>(null);
  const [profileNameDraft,setProfileNameDraft]=useState("");
  const [backupDialogMode,setBackupDialogMode]=useState<"export"|"import"|null>(null);
  const [backupPassword,setBackupPassword]=useState("");
  const [backupPasswordConfirm,setBackupPasswordConfirm]=useState("");
  const [mixedPortDraft,setMixedPortDraft]=useState("10808");
  const [selectedNodeIDs,setSelectedNodeIDs]=useState<Set<string>>(new Set());
  const selectionAnchor=useRef<string|null>(null);
  const [nodeTestResults,setNodeTestResults]=useState<Record<string,NodeTestResult>>({});
  const [nodeSort,setNodeSort]=useState<{key:"tcpPing"|"group"|null;direction:"asc"|"desc"}>({key:null,direction:"asc"});

  useEffect(() => {
    WorkspaceService.GetWorkspace()
      .then(setWorkspace)
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : String(error)));
    WorkspaceService.GetRuntimeStatus().then(setRuntimeStatus).catch(() => undefined);
    WorkspaceService.GetRuntimeLogs().then((logs)=>setRuntimeLogs(logs??[])).catch(() => undefined);
    WorkspaceService.GetProfileState().then(setProfileState).catch((error:unknown)=>setLoadError(error instanceof Error?error.message:String(error)));
    WorkspaceService.GetNodeTestResults().then(results=>setNodeTestResults(Object.fromEntries((results??[]).map(result=>[result.nodeId+":"+result.testType,result])))).catch(()=>undefined);
    const off = Events.On("core:runtime", (event) => {
      const payload = event.data as { type?: string; message?: string; snapshot?: { status: string; pid?: number; lastError?: string } };
      if (payload.type === "log" && payload.message) setRuntimeLogs((current) => [...current.slice(-1999), payload.message!]);
      if (payload.snapshot) setRuntimeStatus(payload.snapshot);
    });
    return off;
  }, []);

  useEffect(()=>{
    const off=Events.On("node:test",event=>{const result=event.data as NodeTestResult;setNodeTestResults(current=>({...current,[result.nodeId+":"+result.testType]:result}))});
    return off;
  },[]);

  useEffect(()=>{if(workspace)setSettingsDraft(structuredClone(workspace.settings))},[workspace?.settings]);
  useEffect(()=>{if(workspace)setMixedPortDraft(String(workspace.settings.baseListenPort))},[workspace?.settings.baseListenPort]);
  useEffect(()=>{if(profileState&&(!selectedProfileID||!profileState.profiles?.some(profile=>profile.id===selectedProfileID)))setSelectedProfileID(profileState.activeProfileId)},[profileState,selectedProfileID]);

  const nodes = workspace?.nodes ?? [];
  const chains = workspace?.chains ?? [];
  const subscriptions = workspace?.subscriptions ?? [];
  const nodeGroups=useMemo(()=>[
    {id:"all",label:"All",count:nodes.length},
    ...(nodes.some(node=>!node.groupId&&(!node.sourceId||!subscriptions.some(sub=>sub.id===node.sourceId)))?[{id:"customs",label:workspace?.settings.customNodesGroupName?.trim()||"Customs",count:nodes.filter(node=>!node.groupId&&(!node.sourceId||!subscriptions.some(sub=>sub.id===node.sourceId))).length}]:[]),
    ...(workspace?.groups??[]).map(group=>({id:group.id,label:group.name,count:nodes.filter(node=>node.groupId===group.id).length})),
    ...subscriptions.map(subscription=>({id:subscription.id,label:subscription.name,count:nodes.filter(node=>node.groupId===subscription.id||(node.sourceId===subscription.id&&(!node.groupId||node.groupId===subscription.id))).length})),
  ],[nodes,subscriptions,workspace?.groups]);
  const getNodeGroupName=(node:Node)=>{
    const group=(workspace?.groups??[]).find(item=>item.id===node.groupId);
    const subscription=subscriptions.find(item=>item.id===node.groupId)||subscriptions.find(item=>item.id===node.sourceId);
    return group?.name??subscription?.name??(node.sourceId?"Unknown source":"Custom");
  };
  const visibleNodes = useMemo(() => {
    const query = filter.trim().toLocaleLowerCase();
    const filtered=nodes.filter(node=>{
      const isSubscriptionGroup=subscriptions.some(subscription=>subscription.id===selectedGroup);
      const matchesGroup=selectedGroup==="all"||(selectedGroup==="customs"?!node.groupId&&(!node.sourceId||!subscriptions.some(sub=>sub.id===node.sourceId)):node.groupId===selectedGroup||(isSubscriptionGroup&&node.sourceId===selectedGroup&&(!node.groupId||node.groupId===selectedGroup)));
      const matchesQuery=!query||[node.name,node.server,node.protocol].some(value=>value.toLocaleLowerCase().includes(query));
      return matchesGroup&&matchesQuery;
    });
    if(nodeSort.key==="tcpPing"){
      filtered.sort((a,b)=>{
        const left=nodeTestResults[a.id+":tcp-ping"];
        const right=nodeTestResults[b.id+":tcp-ping"];
        const leftValue=left?.status==="success"?left.delayMs:Number.POSITIVE_INFINITY;
        const rightValue=right?.status==="success"?right.delayMs:Number.POSITIVE_INFINITY;
        if(!Number.isFinite(leftValue))return Number.isFinite(rightValue)?1:a.name.localeCompare(b.name);
        if(!Number.isFinite(rightValue))return -1;
        if(leftValue===rightValue)return a.name.localeCompare(b.name);
        return (leftValue-rightValue)*(nodeSort.direction==="asc"?1:-1);
      });
    }else if(nodeSort.key==="group"){
      filtered.sort((a,b)=>{
        const compared=getNodeGroupName(a).localeCompare(getNodeGroupName(b),undefined,{numeric:true,sensitivity:"base"});
        if(compared===0)return a.name.localeCompare(b.name);
        return compared*(nodeSort.direction==="asc"?1:-1);
      });
    }
    return filtered;
  }, [filter, nodes, selectedGroup, subscriptions, workspace?.groups, nodeSort, nodeTestResults]);

  const toggleNodeSort=(key:"tcpPing"|"group")=>{
    setNodeSort(current=>current.key===key?{key,direction:current.direction==="asc"?"desc":"asc"}:{key,direction:"asc"});
  };

  const sortHeader=(label:string,key:"tcpPing"|"group")=><button type="button" className="table-sort-button" onClick={()=>toggleNodeSort(key)}>{label}{nodeSort.key===key?(nodeSort.direction==="asc"?<ArrowUp size={12}/>:<ArrowDown size={12}/>):<ArrowUpDown size={12}/>}</button>;

  useEffect(()=>{if(!nodeGroups.some(group=>group.id===selectedGroup))setSelectedGroup("all")},[nodeGroups,selectedGroup]);
  useEffect(()=>{setSelectedNodeIDs(current=>new Set([...current].filter(id=>visibleNodes.some(node=>node.id===id))))},[visibleNodes]);

  useEffect(()=>{
    const keydown=(event:KeyboardEvent)=>{
      if(section!=="nodes"||nodeView!=="base"||contextMenu||nodeEditorOpen||editorOpen||subscriptionManagerOpen)return;
      const target=event.target as HTMLElement|null;
      const tag=target?.tagName?.toLowerCase();
      const editing=tag==="input"||tag==="textarea"||tag==="select"||Boolean(target?.isContentEditable);
      if(editing)return;
      if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="a"){
        event.preventDefault();setSelectedNodeIDs(new Set(visibleNodes.map(node=>node.id)));selectionAnchor.current=visibleNodes[0]?.id??null;return;
      }
      if(event.key==="Escape"){setSelectedNodeIDs(new Set());selectionAnchor.current=null;return}
      if(event.key==="Delete"||event.key==="Backspace"){
        if(selectedNodeIDs.size){event.preventDefault();void deleteSelectedNodes([...selectedNodeIDs])}
      }
    };
    document.addEventListener("keydown",keydown);
    return()=>document.removeEventListener("keydown",keydown);
  },[section,nodeView,contextMenu,nodeEditorOpen,editorOpen,subscriptionManagerOpen,visibleNodes,selectedNodeIDs]);

  useEffect(()=>{
    if(!contextMenu)return;
    const outsidePointer=(event:PointerEvent)=>{
      if(event.button!==0)return;
      if(event.target instanceof Element&&!contextMenuRef.current?.contains(event.target))setContextMenu(null);
    };
    const outsideContext=(event:MouseEvent)=>{
      if(event.target instanceof Element&&!contextMenuRef.current?.contains(event.target))setContextMenu(null);
    };
    const keydown=(event:KeyboardEvent)=>{if(event.key==="Escape")setContextMenu(null)};
    document.addEventListener("pointerdown",outsidePointer,true);
    document.addEventListener("contextmenu",outsideContext,true);
    document.addEventListener("keydown",keydown);
    return()=>{document.removeEventListener("pointerdown",outsidePointer,true);document.removeEventListener("contextmenu",outsideContext,true);document.removeEventListener("keydown",keydown)};
  },[contextMenu]);

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
    await deleteSelectedNodes([nodeID]);
  };

  const deleteSelectedNodes=async(nodeIDs:string[])=>{
    const ids=[...new Set(nodeIDs)];if(!ids.length)return;
    const label=ids.length===1?"this Base Node":ids.length+" selected Base Nodes";
    if(!window.confirm("Delete "+label+"? Nodes used by a Chain cannot be deleted."))return;
    try{setWorkspace(await WorkspaceService.DeleteNodes(ids));setSelectedNodeIDs(new Set());selectionAnchor.current=null;setContextMenu(null);setActionError(null)}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const selectNodeRow=(node:Node,index:number,event:ReactMouseEvent)=>{
    const toggle=event.ctrlKey||event.metaKey;
    if(event.shiftKey){
      const anchorID=selectionAnchor.current??visibleNodes[0]?.id??node.id;
      const anchorIndex=visibleNodes.findIndex(item=>item.id===anchorID);
      const start=anchorIndex<0?0:anchorIndex;
      const end=index;
      const range=visibleNodes.slice(Math.min(start,end),Math.max(start,end)+1).map(item=>item.id);
      setSelectedNodeIDs(current=>new Set(toggle?[...current,...range]:range));
    }else if(toggle){
      setSelectedNodeIDs(current=>{const next=new Set(current);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next});
      selectionAnchor.current=node.id;
    }else{
      setSelectedNodeIDs(new Set([node.id]));
      selectionAnchor.current=node.id;
      void setActiveNode(node.id);
    }
  };

  const runNodeTest=async(type:"tcp-ping"|"real-delay",nodeIDs:string[])=>{
    const ids=[...new Set(nodeIDs)];if(!ids.length)return;setContextMenu(null);
    try{if(type==="tcp-ping")await WorkspaceService.TestNodesTCPPing(ids);else await WorkspaceService.TestNodesRealDelay(ids);setActionError(null)}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const resultFor=(nodeID:string,type:"tcp-ping"|"real-delay")=>nodeTestResults[nodeID+":"+type];

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
    setContextMenu(null);setEditingNode(node);setNodeEditorInitialGroupId(groupId??"");setEditingNodeCredentials({username:"",password:""});
    if(node&&(node.protocol==="socks5"||node.protocol==="http")){
      try{const credentials=await WorkspaceService.GetNodeCredentials(node.id);setEditingNodeCredentials({username:credentials.username??"",password:credentials.password??""})}
      catch(error){setActionError(error instanceof Error?error.message:String(error));return}
    }
    setNodeEditorOpen(true);
  };

  const createNodeGroup=async(name:string)=>{const next=await WorkspaceService.CreateNodeGroup(name);setWorkspace(next);const createdGroup=next.groups?.[next.groups.length-1];setSelectedGroup(createdGroup?.id??"all");setActionError(null)};
  const renameNodeGroup=async(id:string,name:string)=>{setWorkspace(await WorkspaceService.RenameNodeGroup(id,name));setActionError(null)};
  const deleteNodeGroup=async(id:string)=>{setWorkspace(await WorkspaceService.DeleteNodeGroup(id));if(selectedGroup===id)setSelectedGroup("all");setActionError(null)};
  const renameCustomNodesGroup=async(name:string)=>{setWorkspace(await WorkspaceService.RenameCustomNodesGroup(name));setActionError(null)};
  const renameSubscription=async(id:string,name:string)=>{setWorkspace(await WorkspaceService.RenameSubscription(id,name));setActionError(null)};

  const renameGroupFromContext=async(group:{kind:"all"|"custom"|"subscription"|"customs";id:string;name:string})=>{
    setContextMenu(null);
    const name=window.prompt(group.kind==="customs"?"Rename Customs group":group.kind==="custom"?"Rename node group":"Rename subscription group",group.name);
    if(name===null||!name.trim())return;
    try{if(group.kind==="customs")await renameCustomNodesGroup(name.trim());else if(group.kind==="custom")await renameNodeGroup(group.id,name.trim());else await renameSubscription(group.id,name.trim())}catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const removeGroupFromContext=async(group:{kind:"all"|"custom"|"subscription"|"customs";id:string;name:string})=>{
    setContextMenu(null);
    if(group.kind==="customs"||group.kind==="all")return;
    const prompt=group.kind==="custom"?`Delete group "${group.name}"? Nodes will remain and become ungrouped.`:`Delete subscription "${group.name}"? Imported nodes not used by a Chain will be removed.`;
    if(!window.confirm(prompt))return;
    try{if(group.kind==="custom")await deleteNodeGroup(group.id);else{const next=await WorkspaceService.DeleteSubscription(group.id);setWorkspace(next);if(selectedGroup===group.id)setSelectedGroup("all")}}catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const confirmNodeTransfer=async(groupID:string)=>{
    if(!nodeTransfer)return;
    const destinationID=groupID==="__customs__"?"":groupID;
    const next=nodeTransfer.mode==="move"
      ? await WorkspaceService.MoveNodeToGroup(nodeTransfer.node.id,destinationID)
      : await WorkspaceService.CopyNodeToGroup(nodeTransfer.node.id,destinationID);
    setWorkspace(next);
    setActionError(null);
    setNodeTransfer(null);
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

  const saveMixedPort=async()=>{
    if(!workspace)return;
    const port=Number(mixedPortDraft);
    if(!Number.isInteger(port)||port<1||port>65535){setMixedPortDraft(String(workspace.settings.baseListenPort));setActionError("Mixed port must be between 1 and 65535.");return}
    if(port===workspace.settings.baseListenPort)return;
    if(runtimeStatus.status!=="stopped"&&runtimeStatus.status!=="failed"){setMixedPortDraft(String(workspace.settings.baseListenPort));setActionError("Stop the core before changing the mixed listener port.");return}
    try{const next=await WorkspaceService.UpdateSettings({...workspace.settings,baseListenPort:port});setWorkspace(next);setActionError(null);setImportMessage(`Mixed listener port changed to ${port}.`)}
    catch(error){setMixedPortDraft(String(workspace.settings.baseListenPort));setActionError(error instanceof Error?error.message:String(error))}
  };

  const browseCoreExecutable=async()=>{
    if(!settingsDraft)return;
    try{const coreName=settingsDraft.core.type.toLowerCase();const selectedPath=await WorkspaceService.PickCoreExecutable(coreName);if(!selectedPath)return;setSettingsDraft(current=>current?{...current,core:{...current.core,executables:{...(current.core.executables??{}),[coreName]:selectedPath}}}:current);setActionError(null)}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}
  };

  const switchProfile=async(id:string)=>{
    if(!profileState||id===profileState.activeProfileId)return;
    setProfileBusy(true);
    try{const [next,state]=await WorkspaceService.SwitchProfile(id);setWorkspace(next);setProfileState(state);setSelectedGroup("all");setFilter("");setActionError(null);setImportMessage(`Switched to profile ${state.profiles?.find(profile=>profile.id===id)?.name??id}.`)}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setProfileBusy(false)}
  };

  const openCreateProfile=()=>{setProfileNameDraft("");setProfileDialogMode("create")};
  const openRenameProfile=()=>{const current=profileState?.profiles?.find(profile=>profile.id===selectedProfileID);if(!current)return;setProfileNameDraft(current.name);setProfileDialogMode("rename")};
  const submitProfileDialog=async()=>{
    const name=profileNameDraft.trim();if(!name)return;setProfileBusy(true);
    try{if(profileDialogMode==="create"){const next=await WorkspaceService.CreateProfile(name);setProfileState(next);const created=next.profiles?.find(profile=>profile.name===name);if(created)setSelectedProfileID(created.id)}else if(profileDialogMode==="rename"){setProfileState(await WorkspaceService.RenameProfile(selectedProfileID,name))}setActionError(null);setProfileDialogMode(null);setProfileNameDraft("")}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setProfileBusy(false)}
  };

  const deleteProfile=async()=>{
    const selected=profileState?.profiles?.find(profile=>profile.id===selectedProfileID);if(!selected||selected.id==="default"||selected.id===profileState?.activeProfileId)return;
    if(!window.confirm(`Delete profile "${selected.name}" and all of its local workspace data? This cannot be undone.`))return;setProfileBusy(true);
    try{setProfileState(await WorkspaceService.DeleteProfile(selected.id));setActionError(null)}catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setProfileBusy(false)}
  };

  const moveDataLocation=async()=>{
    setProfileBusy(true);
    try{const destination=await WorkspaceService.PickDataLocation();if(!destination||destination===profileState?.dataLocation)return;if(!window.confirm(`Move all ChainPort profiles and data to:\n${destination}\n\nThe current data folder will be retained as a backup.`))return;setProfileState(await WorkspaceService.MoveDataLocation(destination));setActionError(null);setImportMessage("Data copied and switched to the new location. The previous folder was retained as a backup.")}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setProfileBusy(false)}
  };

  const exportSettings=async()=>{try{await WorkspaceService.ExportSettings();setActionError(null)}catch(error){setActionError(error instanceof Error?error.message:String(error))}};
  const importSettings=async()=>{setSettingsBusy(true);try{const next=await WorkspaceService.ImportSettings();if(!next.schemaVersion)return;setWorkspace(next);setSettingsDraft(structuredClone(next.settings));setActionError(null);setImportMessage("Settings imported successfully.")}catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setSettingsBusy(false)}};

  const submitProfileBackup=async()=>{
    if(backupPassword.length<12){setActionError("Backup password must contain at least 12 characters.");return}
    if(backupDialogMode==="export"&&backupPassword!==backupPasswordConfirm){setActionError("Backup passwords do not match.");return}
    setSettingsBusy(true);
    try{if(backupDialogMode==="export"){const exported=await WorkspaceService.ExportProfileBackup(backupPassword);if(exported)setImportMessage("Encrypted profile backup exported.")}else{if(!window.confirm("Restore this backup over the active profile? Its current workspace will be replaced."))return;const next=await WorkspaceService.ImportProfileBackup(backupPassword);if(!next.schemaVersion){setBackupDialogMode(null);setBackupPassword("");setBackupPasswordConfirm("");return}setWorkspace(next);setSettingsDraft(structuredClone(next.settings));setImportMessage("Profile backup restored successfully.")}setActionError(null);setBackupDialogMode(null);setBackupPassword("");setBackupPasswordConfirm("")}
    catch(error){setActionError(error instanceof Error?error.message:String(error))}finally{setSettingsBusy(false)}
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
              <Tabs value={nodeView} onValueChange={(value) => setNodeView(String(value))} className="node-tabs">
                <div className="page-heading nodes-page-heading"><div><div className="eyebrow">ROUTING WORKSPACE</div><h1>Node Groups</h1><p>Manage imported proxy nodes and reusable multi-hop chains.</p></div><div className="nodes-heading-actions"><div className="heading-metrics"><span><strong>{nodes.length}</strong> Base Nodes</span><span><strong>{chains.length}</strong> Chains</span></div><TabsList className="tabs-list"><TabsTrigger value="base" className="tab-trigger"><Network size={15} /> Base</TabsTrigger><TabsTrigger value="chain" className="tab-trigger"><Layers3 size={15} /> Chain</TabsTrigger></TabsList></div></div>
                <TabsContent value="base" className="tab-panel">
                  <div className="panel-heading"><div className="panel-heading-copy"><h2>Base Nodes</h2><p>Single-hop endpoints from manual entries and subscription sources.</p></div><div className="panel-tools"><div className="search-wrap"><Search size={15} /><Input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter nodes…" /></div><label className="mixed-port-control"><span>Mixed</span><Input aria-label="Mixed listener port" type="number" min={1} max={65535} value={mixedPortDraft} disabled={runtimeStatus.status!=="stopped"&&runtimeStatus.status!=="failed"} onChange={event=>setMixedPortDraft(event.target.value)} onBlur={()=>void saveMixedPort()} onKeyDown={event=>{if(event.key==="Enter")event.currentTarget.blur()}}/></label>{nodes.length===0&&subscriptions.length===0&&<Button variant="outline" onClick={()=>void importLegacyState()}>Import Legacy State</Button>}<Button variant="outline" onClick={()=>setSubscriptionManagerOpen(true)}><Rss size={14}/> Subscriptions</Button></div></div>
                  <div className="node-group-bar" role="tablist" aria-label="Node groups"><div className="node-group-chips">{nodeGroups.map(group=><button key={group.id} className={`group-chip ${selectedGroup===group.id?"active":""}`} onClick={()=>setSelectedGroup(group.id)} onContextMenu={event=>{const customGroup=(workspace?.groups??[]).find(item=>item.id===group.id);const subscription=(workspace?.subscriptions??[]).find(item=>item.id===group.id);const isCustoms=group.id==="customs";const isAll=group.id==="all";if(!customGroup&&!subscription&&!isCustoms&&!isAll)return;event.preventDefault();event.stopPropagation();setContextMenu({kind:"group",group:{kind:isAll?"all":isCustoms?"customs":customGroup?"custom":"subscription",id:group.id,name:group.label},x:Math.max(8,Math.min(event.clientX,window.innerWidth-230)),y:Math.max(8,Math.min(event.clientY,window.innerHeight-170))})}} role="tab" aria-selected={selectedGroup===group.id}>{group.label}<span>{group.count}</span></button>)}</div><div className="node-list-actions">{selectedNodeIDs.size>0&&<><span className="selection-count">{selectedNodeIDs.size} selected</span><Button size="sm" variant="ghost" onClick={()=>{setSelectedNodeIDs(new Set());selectionAnchor.current=null}}>Clear</Button><Button size="sm" variant="destructive" onClick={()=>void deleteSelectedNodes([...selectedNodeIDs])}><Trash2 size={13}/> Delete</Button></>}{selectedNodeIDs.size===0&&<span className="selection-help">Ctrl/⌘ select · Shift range · Ctrl+A all · Del delete</span>}<Button size="sm" variant="outline" onClick={()=>setGroupManagerOpen(true)}><Plus size={14}/> Create Group</Button></div></div>
                  {loadError ? <div className="error-panel">Could not load workspace: {loadError}</div> : <Card className="table-card node-list-card"><CardContent className="table-content"><Table className="data-table node-list-table"><TableHeader><TableRow><TableHead>TYPE</TableHead><TableHead>REMARKS</TableHead><TableHead>ADDRESS</TableHead><TableHead>PORT</TableHead><TableHead>TRANSPORT</TableHead><TableHead>TLS</TableHead><TableHead>{sortHeader("TCP PING","tcpPing")}</TableHead><TableHead>REAL DELAY</TableHead><TableHead>{sortHeader("GROUP / SOURCE","group")}</TableHead><TableHead>ACTIVE</TableHead><TableHead>ACTIONS</TableHead></TableRow></TableHeader><TableBody>{visibleNodes.map((node,index)=>{const source=subscriptions.find(item=>item.id===node.sourceId);const group=(workspace?.groups??[]).find(item=>item.id===node.groupId);const assignedSubscription=subscriptions.find(item=>item.id===node.groupId);const groupLabel=[group?.name,assignedSubscription?.name,source?.name??(node.sourceId?"Unknown source":null)].filter(Boolean).filter((value,index,array)=>array.indexOf(value)===index).join(" · ")||"Custom";const tcp=resultFor(node.id,"tcp-ping");const real=resultFor(node.id,"real-delay");const selected=selectedNodeIDs.has(node.id);return <TableRow key={node.id} data-active={workspace?.activeNodeId===node.id} data-selected={selected} aria-selected={selected} onClick={event=>selectNodeRow(node,index,event)} onDoubleClick={()=>void openNodeEditor(node)} onContextMenu={event=>{event.preventDefault();event.stopPropagation();const ids=selectedNodeIDs.has(node.id)?[...selectedNodeIDs]:[node.id];if(!selectedNodeIDs.has(node.id)){setSelectedNodeIDs(new Set([node.id]));selectionAnchor.current=node.id}setContextMenu({kind:"node",node,nodeIDs:ids,x:Math.max(8,Math.min(event.clientX,window.innerWidth-245)),y:Math.max(8,Math.min(event.clientY,window.innerHeight-430))})}} className="node-data-row"><TableCell><span className="protocol-pill">{node.protocol}</span></TableCell><TableCell className="cell-strong">{node.name}</TableCell><TableCell className="mono">{node.server}</TableCell><TableCell className="mono">{node.port}</TableCell><TableCell>{node.transport?.network||"tcp"}</TableCell><TableCell>{node.tls?.enabled?"TLS":"—"}</TableCell><TableCell className="test-result-cell" title={tcp?.error??"TCP connection test"}>{tcp?.status==="testing"?"Testing…":tcp?.status==="success"?<span className="test-success">{tcp.delayMs} ms</span>:tcp?.status==="failed"?<span className="test-failed">-1 ms</span>:tcp?.status==="cancelled"?<span className="test-failed">Cancelled</span>:"—"}</TableCell><TableCell className="test-result-cell" title={real?.error??"HTTP request through this proxy"}>{real?.status==="testing"?"Testing…":real?.status==="success"?<span className="test-success">{real.delayMs} ms</span>:real?.status==="failed"?<span className="test-failed">-1 ms</span>:real?.status==="cancelled"?<span className="test-failed">Cancelled</span>:"—"}</TableCell><TableCell>{groupLabel}</TableCell><TableCell>{workspace?.activeNodeId===node.id?<span className="active-node-pill"><Check size={12}/> Active</span>:"—"}</TableCell><TableCell><div className="row-actions"><Button size="icon-sm" variant="ghost" title="Edit node" aria-label={`Edit ${node.name}`} onClick={event=>{event.stopPropagation();void openNodeEditor(node)}}><Pencil size={14}/></Button><Button size="icon-sm" variant="ghost" title="Delete node" aria-label={`Delete ${node.name}`} className="node-delete-action" onClick={event=>{event.stopPropagation();void deleteNode(node.id)}}><Trash2 size={14}/></Button></div></TableCell></TableRow>})}</TableBody></Table>{visibleNodes.length===0&&<div className="empty-state"><div className="empty-icon"><Network size={22}/></div><strong>{filter?"No matching nodes":selectedGroup==="all"?"No Base Nodes yet":"This group has no nodes"}</strong><span>{filter?"Try a different search term.":"Add a node or import a subscription to get started."}</span></div>}</CardContent></Card>}
                </TabsContent>
                <TabsContent value="chain" className="tab-panel">
                  <div className="panel-heading"><div><h2>Chain Nodes</h2><p>Compose ordered routes. Each saved Chain owns one local listener.</p></div><Button onClick={() => { setEditingChain(undefined); setEditorOpen(true); }} disabled={nodes.length === 0}>Create Chain</Button></div>
                  <Card className="table-card"><CardContent className="table-content"><Table className="data-table"><TableHeader><TableRow><TableHead>NAME</TableHead><TableHead>ROUTE · ENTRY → EXIT</TableHead><TableHead>LOCAL PORT</TableHead><TableHead>HOPS</TableHead><TableHead>TUN</TableHead><TableHead>ACTIONS</TableHead></TableRow></TableHeader><TableBody>{chains.map((chain) => { const hopIDs = chain.hopNodeIds ?? []; const port = (workspace?.portBindings ?? []).find((binding) => binding.chainId === chain.id)?.listenPort; return <TableRow key={chain.id} onDoubleClick={()=>editChain(chain)} onContextMenu={event=>{event.preventDefault();event.stopPropagation();setContextMenu({kind:"chain",chain,x:Math.max(8,Math.min(event.clientX,window.innerWidth-220)),y:Math.max(8,Math.min(event.clientY,window.innerHeight-190))})}} className="node-data-row"><TableCell className="cell-strong">{chain.name}</TableCell><TableCell>{hopIDs.map((id) => nodes.find((node) => node.id === id)?.name ?? "Missing node").join(" → ")}</TableCell><TableCell className="mono">{port ?? "—"}</TableCell><TableCell>{hopIDs.length}</TableCell><TableCell>{workspace?.tun.kind === "chain" && workspace.tun.targetId === chain.id ? <span className="bound-pill">BOUND</span> : "—"}</TableCell><TableCell><div className="row-actions"><Button variant="ghost" size="sm" onClick={() => editChain(chain)} title="Edit Chain"><Pencil size={14} /></Button><Button variant="outline" size="sm" onClick={() => void bindChainTUN(chain.id)} title="Set this complete Chain as the TUN route target"><ShieldCheck size={13} /> Bind TUN</Button><Button variant="ghost" size="sm" onClick={()=>void deleteChain(chain.id)}>Delete</Button></div></TableCell></TableRow>; })}</TableBody></Table>{chains.length === 0 && <div className="empty-state"><div className="empty-icon"><Layers3 size={22} /></div><strong>No Chains created</strong><span>Create a Chain to combine Base Nodes into an ordered route.</span></div>}</CardContent></Card>
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
                    <label className="form-label">Remote DNS (HTTPS)<Input value={settingsDraft.network.remoteDNSUrl} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,remoteDNSUrl:e.target.value}})}/></label>
                    <label className="form-label">Bootstrap DNS<Input value={settingsDraft.network.bootstrapDNS} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,bootstrapDNS:e.target.value}})}/></label>
                  </CardContent></Card>
                  <Card><CardHeader className="compact-card-header"><CardTitle><Shield size={17}/> Network Features</CardTitle></CardHeader><CardContent>
                    <div className="network-toggle-grid">
                      {([ ["enableUDP","UDP forwarding"],["enableIPv6","IPv6"],["enableSniffing","Protocol sniffing"],["allowLAN","Allow LAN"],["enableMux","Multiplexing"],["allowInsecure","Allow insecure TLS"],["enableFragment","TLS fragmentation"],["enableFinalFragment","Final outbound fragmentation"],["blockQUIC","Block QUIC"] ] as const).map(([key,label])=><label className="setting-toggle compact-setting-toggle" key={key}><span>{label}</span><input type="checkbox" checked={settingsDraft.network[key]} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,[key]:e.target.checked}})}/></label>)}
                    </div>
                    <details className="advanced-network-settings"><summary>Advanced protocol settings</summary><div className="advanced-network-grid">
                      <label className="form-label">sing-box mux protocol<Select value={settingsDraft.network.singboxMuxProtocol||"h2mux"} onValueChange={value=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,singboxMuxProtocol:String(value)}})}><SelectTrigger className="native-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="h2mux">h2mux</SelectItem><SelectItem value="smux">smux</SelectItem><SelectItem value="yamux">yamux</SelectItem></SelectContent></Select></label>
                      <label className="form-label">Xray fragment packet mode<Select value={settingsDraft.network.xrayFragmentPackets||"tlshello"} onValueChange={value=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentPackets:String(value)}})}><SelectTrigger className="native-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="tlshello">TLS Hello</SelectItem><SelectItem value="1-3">First 1–3 packets</SelectItem></SelectContent></Select></label>
                      <label className="form-label">Xray fragment lengths<Input value={(settingsDraft.network.xrayFragmentLengths??[]).join(",")} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentLengths:e.target.value.split(",").map(value=>value.trim()).filter(Boolean)}})} placeholder="50-100"/></label>
                      <label className="form-label">Xray fragment delays (ms)<Input value={(settingsDraft.network.xrayFragmentDelays??[]).join(",")} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentDelays:e.target.value.split(",").map(value=>value.trim()).filter(Boolean)}})} placeholder="10-20"/></label>
                      <label className="form-label">Xray max split<Input type="number" min={0} max={64} value={settingsDraft.network.xrayFragmentMaxSplit??0} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,xrayFragmentMaxSplit:Number(e.target.value)}})}/></label>
                      <label className="form-label">Real delay test URL<Input value={settingsDraft.network.speedPingTestUrl??"https://www.google.com/generate_204"} onChange={e=>setSettingsDraft({...settingsDraft,network:{...settingsDraft.network,speedPingTestUrl:e.target.value}})} placeholder="https://www.google.com/generate_204"/></label>
                    </div></details>
                  </CardContent></Card>
                  <Card><CardHeader className="compact-card-header"><CardTitle><Settings2 size={17}/> Application</CardTitle></CardHeader><CardContent>
                    <div className="application-toggle-grid">{([ ["autoStart","Start core on application launch"],["runOnStartup","Run application on system startup"],["minimizeOnStart","Start minimized"],["closeToTray","Close to system tray"] ] as const).map(([key,label])=><label className="setting-toggle compact-setting-toggle" key={key}><span>{label}</span><input type="checkbox" checked={settingsDraft[key]} onChange={e=>setSettingsDraft({...settingsDraft,[key]:e.target.checked})}/></label>)}</div>
                    <p className="compact-setting-help">Startup registration and window behavior changes take effect on the next application launch.</p>
                  </CardContent></Card>
                  <Card className="settings-management-card"><CardHeader className="compact-card-header"><CardTitle><Database size={17}/> Profiles, Data & Backup</CardTitle></CardHeader><CardContent>
                    <div className="settings-management-grid">
                      <section className="management-section"><div className="management-title"><Layers3 size={14}/> Profiles</div>
                        <Select value={selectedProfileID||(profileState?.activeProfileId??"default")} onValueChange={value=>setSelectedProfileID(String(value))} disabled={profileBusy||!profileState}><SelectTrigger className="native-select"><SelectValue placeholder="Select profile"/></SelectTrigger><SelectContent>{(profileState?.profiles??[]).map(profile=><SelectItem key={profile.id} value={profile.id}>{profile.name}{profile.id===profileState?.activeProfileId?" · Active":profile.id==="default"?" · Default":""}</SelectItem>)}</SelectContent></Select>
                        <div className="row-actions management-actions"><Button type="button" size="sm" onClick={()=>void switchProfile(selectedProfileID)} disabled={profileBusy||!profileState||selectedProfileID===profileState.activeProfileId}>Switch</Button><Button type="button" variant="outline" size="sm" onClick={openCreateProfile} disabled={profileBusy}>New</Button><Button type="button" variant="outline" size="sm" onClick={openRenameProfile} disabled={profileBusy}>Rename</Button><Button type="button" variant="outline" size="sm" onClick={()=>void deleteProfile()} disabled={profileBusy||selectedProfileID==="default"||selectedProfileID===profileState?.activeProfileId}>Delete</Button></div>
                        {selectedProfileID===profileState?.activeProfileId&&selectedProfileID!=="default"&&<p className="management-hint">Switch away before deleting.</p>}
                      </section>
                      <section className="management-section"><div className="management-title"><FolderOpen size={14}/> Data Location</div><div className="data-location-value" title={profileState?.dataLocation}>{profileState?.dataLocation??"Loading…"}</div><Button type="button" variant="outline" size="sm" onClick={()=>void moveDataLocation()} disabled={profileBusy||!profileState}>Move data…</Button></section>
                      <section className="management-section"><div className="management-title"><Download size={14}/> Settings JSON</div><p className="management-hint">Preferences only; no nodes or credentials.</p><div className="row-actions management-actions"><Button type="button" variant="outline" size="sm" onClick={()=>void exportSettings()} disabled={settingsBusy}><Download size={13}/> Export</Button><Button type="button" variant="outline" size="sm" onClick={()=>void importSettings()} disabled={settingsBusy}><Upload size={13}/> Import</Button></div></section>
                      <section className="management-section"><div className="management-title"><KeyRound size={14}/> Full Profile Backup</div><p className="management-hint">Includes credentials; password encrypted.</p><div className="row-actions management-actions"><Button type="button" variant="outline" size="sm" onClick={()=>{setBackupDialogMode("export");setBackupPassword("");setBackupPasswordConfirm("")}} disabled={settingsBusy}><Download size={13}/> Backup</Button><Button type="button" variant="outline" size="sm" onClick={()=>{setBackupDialogMode("import");setBackupPassword("");setBackupPasswordConfirm("")}} disabled={settingsBusy}><Upload size={13}/> Restore</Button></div></section>
                    </div>
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
      {contextMenu?.kind==="node"&&<div ref={contextMenuRef} className="node-context-menu" style={{left:contextMenu.x,top:contextMenu.y}} onContextMenu={event=>event.preventDefault()}>
        <div className="context-menu-title">{contextMenu.nodeIDs.length>1?contextMenu.nodeIDs.length+" selected Base Nodes":contextMenu.node.name}</div>
        {contextMenu.nodeIDs.length===1&&<><button onClick={()=>{void setActiveNode(contextMenu.node.id);setContextMenu(null)}}><Check size={14}/> Set as active</button><button onClick={()=>{void bindNodeTUN(contextMenu.node.id);setContextMenu(null)}}><ShieldCheck size={14}/> Bind TUN to this node</button><div className="context-menu-separator"/><button onClick={()=>{void openNodeEditor(contextMenu.node);setContextMenu(null)}}><Edit3 size={14}/> Edit</button><button onClick={()=>{const node=contextMenu.node;setContextMenu(null);setNodeTransfer({node,mode:"copy"})}}><Copy size={14}/> Clone selected</button><button onClick={()=>{const node=contextMenu.node;setContextMenu(null);setNodeTransfer({node,mode:"move"})}}><FolderInput size={14}/> Move to…</button><div className="context-menu-separator"/></>}
        <button onClick={()=>void runNodeTest("tcp-ping",contextMenu.nodeIDs)}><Activity size={14}/> Test TCP ping</button>
        <button onClick={()=>void runNodeTest("real-delay",contextMenu.nodeIDs)}><Activity size={14}/> Test real delay</button>
        <div className="context-menu-separator"/>
        <button className="context-menu-danger" onClick={()=>void deleteSelectedNodes(contextMenu.nodeIDs)}><Trash2 size={14}/> Delete {contextMenu.nodeIDs.length>1?"selected":"node"}</button>
      </div>}
      {contextMenu?.kind==="group"&&<div ref={contextMenuRef} className="node-context-menu" style={{left:contextMenu.x,top:contextMenu.y}} onContextMenu={event=>event.preventDefault()}>
        <div className="context-menu-title">{contextMenu.group.name}</div>
        {contextMenu.group.kind!=="subscription"&&<button onClick={()=>{const group=contextMenu.group;setContextMenu(null);void openNodeEditor(undefined,group.kind==="customs"||group.kind==="all"?"":group.id)}}><Plus size={14}/> Add Node to Group</button>}
        {contextMenu.group.kind!=="all"&&<button onClick={()=>void renameGroupFromContext(contextMenu.group)}><Edit3 size={14}/> Rename Group</button>}
        {contextMenu.group.kind!=="customs"&&contextMenu.group.kind!=="all"&&<><div className="context-menu-separator"/><button className="context-menu-danger" onClick={()=>void removeGroupFromContext(contextMenu.group)}><Trash2 size={14}/> Delete Group</button></>}
      </div>}
      {contextMenu?.kind==="chain"&&<div ref={contextMenuRef} className="node-context-menu" style={{left:contextMenu.x,top:contextMenu.y}} onContextMenu={event=>event.preventDefault()}>
        <div className="context-menu-title">{contextMenu.chain.name}</div>
        <button onClick={()=>{editChain(contextMenu.chain);setContextMenu(null)}}><Edit3 size={14}/> Edit Chain</button>
        <button onClick={()=>{void bindChainTUN(contextMenu.chain.id);setContextMenu(null)}}><ShieldCheck size={14}/> Bind TUN to this Chain</button>
        <div className="context-menu-separator"/>
        <button className="context-menu-danger" onClick={()=>void deleteChain(contextMenu.chain.id).finally(()=>setContextMenu(null))}><Trash2 size={14}/> Remove Chain</button>
        <button onClick={()=>{setEditingChain(undefined);setEditorOpen(true);setContextMenu(null)}}><Plus size={14}/> Create Chain</button>
      </div>}
      <ChainEditorDialog open={editorOpen} nodes={nodes} chain={editingChain} listenPort={editingChain ? (workspace?.portBindings ?? []).find((binding) => binding.chainId === editingChain.id)?.listenPort : undefined} onOpenChange={setEditorOpen} onSave={saveChain} />
      <Dialog open={profileDialogMode!==null} onOpenChange={open=>{if(!open){setProfileDialogMode(null);setProfileNameDraft("")}}}>
        <DialogContent showCloseButton>
          <div className="dialog-heading"><div><DialogTitle>{profileDialogMode==="create"?"Create Profile":"Rename Profile"}</DialogTitle><DialogDescription>{profileDialogMode==="create"?"Create an independent workspace with its own Nodes, Chains and subscriptions.":"Choose a new name for this profile."}</DialogDescription></div></div>
          <label className="form-label">Profile name<Input autoFocus value={profileNameDraft} maxLength={128} onChange={event=>setProfileNameDraft(event.target.value)} placeholder="e.g. Work, Home, Travel" onKeyDown={event=>{if(event.key==="Enter")void submitProfileDialog()}}/></label>
          <div className="dialog-actions"><Button variant="outline" onClick={()=>setProfileDialogMode(null)}>Cancel</Button><Button onClick={()=>void submitProfileDialog()} disabled={profileBusy||!profileNameDraft.trim()}>{profileBusy?"Saving…":profileDialogMode==="create"?"Create Profile":"Save Name"}</Button></div>
        </DialogContent>
      </Dialog>
      <Dialog open={backupDialogMode!==null} onOpenChange={open=>{if(!open){setBackupDialogMode(null);setBackupPassword("");setBackupPasswordConfirm("")}}}>
        <DialogContent showCloseButton>
          <div className="dialog-heading"><div><DialogTitle>{backupDialogMode==="export"?"Export Encrypted Profile Backup":"Restore Encrypted Profile Backup"}</DialogTitle><DialogDescription>{backupDialogMode==="export"?"Choose a strong password. You will need it to restore this backup on this or another computer.":"Enter the password used when this profile backup was created."}</DialogDescription></div></div>
          <label className="form-label">Backup password<Input type="password" autoComplete="new-password" value={backupPassword} onChange={event=>setBackupPassword(event.target.value)} placeholder="At least 12 characters"/></label>
          {backupDialogMode==="export"&&<label className="form-label">Confirm password<Input type="password" autoComplete="new-password" value={backupPasswordConfirm} onChange={event=>setBackupPasswordConfirm(event.target.value)} placeholder="Re-enter backup password"/></label>}
          <div className="dialog-actions"><Button variant="outline" onClick={()=>setBackupDialogMode(null)}>Cancel</Button><Button onClick={()=>void submitProfileBackup()} disabled={settingsBusy||backupPassword.length<12}>{settingsBusy?"Working…":backupDialogMode==="export"?"Export Backup":"Restore Profile"}</Button></div>
        </DialogContent>
      </Dialog>
      <NodeEditorDialog open={nodeEditorOpen} node={editingNode} groups={workspace?.groups??[]} subscriptions={subscriptions} credentials={editingNodeCredentials} initialGroupId={nodeEditorInitialGroupId} onOpenChange={open=>{setNodeEditorOpen(open);if(!open){setEditingNode(undefined);setNodeEditorInitialGroupId("");setEditingNodeCredentials({username:"",password:""})}}} onSave={saveNode} />
      <NodeGroupTransferDialog open={nodeTransfer!==null} mode={nodeTransfer?.mode??"move"} nodeName={nodeTransfer?.node.name??""} groups={[...(workspace?.groups??[]),{id:"__customs__",name:`${workspace?.settings.customNodesGroupName?.trim()||"Customs"} (ungrouped)`}]} onOpenChange={open=>{if(!open)setNodeTransfer(null)}} onConfirm={confirmNodeTransfer}/>
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
