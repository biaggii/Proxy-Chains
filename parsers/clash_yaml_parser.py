"""
clash_yaml_parser.py — 解析 Clash 訂閱（YAML 格式）

Clash 訂閱就是一個 YAML 文件，裡面有一個 "proxies" 清單，
每個元素是一個 dict，描述一個代理節點的資訊。

這個模組做的事情：
1. 把 YAML 文字解析成 Python dict
2. 找到 "proxies" 清單
3. 把每個 proxy dict 轉成我們的 Node 物件
"""


import yaml

from models.node import (
    Node,
    NODE_TYPE_VMESS,
    NODE_TYPE_VLESS,
    NODE_TYPE_TROJAN,
    NODE_TYPE_SS,
    NODE_TYPE_WG,
    NODE_TYPE_SOCKS5,
    NODE_TYPE_HTTP,
    NODE_TYPE_UNKNOWN,
)


# ============================================================
# Clash proxy type 對應到我們的 node_type
# ============================================================
CLASH_TYPE_MAP: dict[str, str] = {
    "vmess": NODE_TYPE_VMESS,
    "vless": NODE_TYPE_VLESS,
    "trojan": NODE_TYPE_TROJAN,
    "ss": NODE_TYPE_SS,
    "shadowsocks": NODE_TYPE_SS,
    "wireguard": NODE_TYPE_WG,
    "wg": NODE_TYPE_WG,
    "socks5": NODE_TYPE_SOCKS5,
    "socks": NODE_TYPE_SOCKS5,
    "http": NODE_TYPE_HTTP,
    "https": NODE_TYPE_HTTP,
}


def parse_clash_yaml(
    yaml_text: str,
    source_sub_name: str = "",
) -> tuple[list[Node], list[str]]:
    """
    解析 Clash YAML 訂閱文字。

    參數：
    - yaml_text       : 完整的 YAML 文字內容
    - source_sub_name : 來源訂閱名稱（寫進每個 Node 的 source_sub）

    回傳值：
    - (成功的節點清單, 錯誤訊息清單)
    - 錯誤訊息清單裡的每一筆都會說明「第幾個 proxy、名稱、原因」
    """
    # --- 第 1 步：解析 YAML ---
    try:
        yaml_data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as err:
        error_msg = f"YAML parse failed (subscription: {source_sub_name}): {err}"
        return [], [error_msg]

    # --- 第 2 步：檢查根結構 ---
    if not isinstance(yaml_data, dict):
        return [], [f"YAML root is not a dict (subscription: {source_sub_name})"]

    # 找 "proxies" 清單
    proxy_list = yaml_data.get("proxies")
    if proxy_list is None:
        return [], [f"Missing 'proxies' field in YAML (subscription: {source_sub_name})"]

    if not isinstance(proxy_list, list):
        return [], [f"'proxies' is not a list (subscription: {source_sub_name})"]

    if len(proxy_list) == 0:
        return [], [f"'proxies' list is empty (subscription: {source_sub_name})"]

    # --- 第 3 步：逐一轉換 ---
    good_nodes: list[Node] = []
    error_messages: list[str] = []

    for index, proxy_dict in enumerate(proxy_list):
        try:
            node = _convert_one_clash_proxy(proxy_dict, index, source_sub_name)
            good_nodes.append(node)
        except Exception as err:
            # 記下錯誤但繼續處理下一個
            proxy_name = proxy_dict.get("name", "Unknown") if isinstance(proxy_dict, dict) else "non-dict"
            error_messages.append(
                f"Failed to parse proxy #{index + 1} (name={proxy_name}): {err}"
            )

    return good_nodes, error_messages


def _convert_one_clash_proxy(
    proxy_dict: dict,
    index: int,
    source_sub_name: str,
) -> Node:
    """
    把一個 Clash proxy dict 轉成 Node。
    如果缺少必要欄位就拋 ValueError。
    """
    # 檢查是不是 dict
    if not isinstance(proxy_dict, dict):
        raise ValueError(f"Proxy is not a dict, got {type(proxy_dict).__name__}")

    # --- 必要欄位 ---
    proxy_name = str(proxy_dict.get("name", f"Unnamed-{index + 1}"))
    clash_type = str(proxy_dict.get("type", "")).lower()
    server_address = str(proxy_dict.get("server", ""))
    server_port = int(proxy_dict.get("port", 0))

    if not server_address:
        raise ValueError("Missing 'server' field")
    if server_port < 1:
        raise ValueError("Missing or invalid 'port' field")

    # 對應到我們的 node_type
    node_type = CLASH_TYPE_MAP.get(clash_type, NODE_TYPE_UNKNOWN)

    # --- 可選欄位（根據類型不同而不同） ---
    uuid_str = _get_str(proxy_dict, "uuid")
    password = _get_str(proxy_dict, "password")
    cipher = _get_str(proxy_dict, "cipher")
    network_type = _get_str(proxy_dict, "network") or "tcp"
    tls_enabled = bool(proxy_dict.get("tls", False))
    sni_value = _get_str(proxy_dict, "sni") or _get_str(proxy_dict, "servername")
    alpn_value = proxy_dict.get("alpn")
    skip_cert = proxy_dict.get("skip-cert-verify", False)

    # WebSocket 相關
    ws_opts = proxy_dict.get("ws-opts") or proxy_dict.get("ws-opt") or {}
    ws_path = _get_str(ws_opts, "path") if isinstance(ws_opts, dict) else None
    ws_headers = ws_opts.get("headers", {}) if isinstance(ws_opts, dict) else {}
    ws_host = _get_str(ws_headers, "Host") if isinstance(ws_headers, dict) else None

    # HTTP/2 相關
    h2_opts = proxy_dict.get("h2-opts") or {}
    h2_path = _get_str(h2_opts, "path") if isinstance(h2_opts, dict) else None
    h2_host_list = h2_opts.get("host", []) if isinstance(h2_opts, dict) else []
    h2_host = h2_host_list[0] if h2_host_list else None

    # gRPC 相關
    grpc_opts = proxy_dict.get("grpc-opts") or {}
    grpc_service = _get_str(grpc_opts, "grpc-service-name") if isinstance(grpc_opts, dict) else None

    # 彙整 path / host
    final_path = ws_path or h2_path or grpc_service
    final_host = ws_host or h2_host

    # VLESS flow
    flow_value = _get_str(proxy_dict, "flow")

    # 使用者名稱（socks5/http 用）
    username = _get_str(proxy_dict, "username")

    # alterID
    alter_id_value = int(proxy_dict.get("alterId", 0))

    # WireGuard 相關
    wg_public_key = _get_str(proxy_dict, "public-key")
    wg_private_key = _get_str(proxy_dict, "private-key")
    wg_ip = _get_str(proxy_dict, "ip")
    wg_ipv6 = _get_str(proxy_dict, "ipv6")
    wg_local_addr = wg_ip if wg_ip else wg_ipv6

    # SS 插件（obfs / v2ray-plugin）
    plugin = _get_str(proxy_dict, "plugin")
    plugin_opts = proxy_dict.get("plugin-opts")
    extra_data = {"skip_cert_verify": skip_cert}
    if plugin:
        extra_data["plugin"] = plugin
        if isinstance(plugin_opts, dict):
            extra_data["plugin_opts"] = plugin_opts

    return Node(
        name=proxy_name,
        node_type=node_type,
        server=server_address,
        port=server_port,
        uuid_str=uuid_str,
        password=password,
        username=username,
        encryption=cipher,
        alter_id=alter_id_value,
        tls_enabled=tls_enabled,
        sni=sni_value,
        alpn=alpn_value if isinstance(alpn_value, list) else None,
        path=final_path,
        host=final_host,
        network=network_type,
        flow=flow_value,
        wg_public_key=wg_public_key,
        wg_private_key=wg_private_key,
        wg_local_address=wg_local_addr,
        extra=extra_data,
        raw_dict=proxy_dict,
        source_sub=source_sub_name,
    )


def _get_str(d: dict, key: str) -> str | None:
    """從 dict 安全地取字串，None 或空字串都回傳 None"""
    val = d.get(key)
    if val is None:
        return None
    val_str = str(val).strip()
    return val_str if val_str else None
