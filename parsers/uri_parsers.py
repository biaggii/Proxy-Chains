"""
uri_parsers.py — 解析各種代理分享鏈接（URI）

每種協議（vmess://、vless://、trojan://、ss://、socks5://、http://）
都有自己的 parse 函式，輸入一行 URI 字串，輸出一個 Node。

如果解析失敗，會拋出 ValueError 並附上清楚的錯誤訊息。
"""

import base64
import json
import urllib.parse

from models.node import (
    Node,
    NODE_TYPE_VMESS,
    NODE_TYPE_VLESS,
    NODE_TYPE_TROJAN,
    NODE_TYPE_SS,
    NODE_TYPE_SOCKS5,
    NODE_TYPE_HTTP,
)


# ============================================================
# 工具函式
# ============================================================

def _safe_base64_decode(encoded_text: str) -> str:
    """
    安全地解碼 base64 字串。
    有些分享鏈的 base64 末尾缺少 padding（=），這裡自動補上。
    """
    # 去掉空白
    encoded_text = encoded_text.strip()
    # 補齊 padding（base64 長度必須是 4 的倍數）
    missing_padding = len(encoded_text) % 4
    if missing_padding:
        encoded_text += "=" * (4 - missing_padding)
    try:
        raw_bytes = base64.b64decode(encoded_text)
        return raw_bytes.decode("utf-8", errors="replace")
    except Exception as err:
        raise ValueError(f"Base64 解碼失敗: {err}")


def _parse_int_safe(value: str, field_name: str) -> int:
    """安全地把字串轉成整數，失敗就報錯"""
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"欄位 '{field_name}' 無法轉成數字: '{value}'")


# ============================================================
# vmess:// 解析
# ============================================================

def parse_vmess_uri(uri: str, source_sub: str = "") -> Node:
    """
    解析 vmess:// 分享鏈。
    格式：vmess://BASE64_JSON
    BASE64 解碼後是一個 JSON 物件，裡面有 v, ps, add, port, id, aid, net, type, host, path, tls...
    """
    # 去掉前綴 "vmess://"
    encoded_part = uri[len("vmess://"):].strip()

    # base64 解碼
    decoded_text = _safe_base64_decode(encoded_part)

    # 解析 JSON
    try:
        vmess_json = json.loads(decoded_text)
    except json.JSONDecodeError as err:
        raise ValueError(f"vmess:// 的 base64 解碼後不是合法 JSON: {err}")

    # 取出各欄位（容錯：用 get 並給預設值）
    node_name = str(vmess_json.get("ps", "vmess 節點"))
    server_address = str(vmess_json.get("add", ""))
    server_port = _parse_int_safe(vmess_json.get("port", 0), "port")
    node_uuid = str(vmess_json.get("id", ""))
    alter_id_value = int(vmess_json.get("aid", 0))
    network_type = str(vmess_json.get("net", "tcp"))
    tls_value = str(vmess_json.get("tls", ""))
    sni_value = str(vmess_json.get("sni", ""))
    host_value = str(vmess_json.get("host", ""))
    path_value = str(vmess_json.get("path", ""))
    security_value = str(vmess_json.get("scy", "auto"))

    # 檢查必要欄位
    if not server_address:
        raise ValueError("vmess:// 缺少 'add'（伺服器地址）")
    if not node_uuid:
        raise ValueError("vmess:// 缺少 'id'（UUID）")

    # 判斷 TLS 是否啟用
    is_tls = tls_value.lower() in ("tls", "true", "1")

    return Node(
        name=node_name,
        node_type=NODE_TYPE_VMESS,
        server=server_address,
        port=server_port,
        uuid_str=node_uuid,
        alter_id=alter_id_value,
        tls_enabled=is_tls,
        sni=sni_value if sni_value else None,
        host=host_value if host_value else None,
        path=path_value if path_value else None,
        network=network_type,
        security=security_value,
        raw_dict=vmess_json,
        source_sub=source_sub,
    )


# ============================================================
# vless:// 解析
# ============================================================

def parse_vless_uri(uri: str, source_sub: str = "") -> Node:
    """
    解析 vless:// 分享鏈。
    格式：vless://UUID@SERVER:PORT?params#NAME
    """
    # 去掉前綴
    without_scheme = uri[len("vless://"):]

    # 先拆 fragment（# 後面的是名稱）
    if "#" in without_scheme:
        main_part, fragment = without_scheme.rsplit("#", 1)
        node_name = urllib.parse.unquote(fragment)
    else:
        main_part = without_scheme
        node_name = "vless 節點"

    # 拆 userinfo@host:port?query
    # userinfo 就是 UUID
    at_index = main_part.find("@")
    if at_index < 0:
        raise ValueError("vless:// 格式錯誤：找不到 '@'")

    user_info = main_part[:at_index]    # UUID
    rest = main_part[at_index + 1:]      # host:port?query

    # 拆 query
    if "?" in rest:
        host_port_str, query_str = rest.split("?", 1)
        query_params = urllib.parse.parse_qs(query_str)
    else:
        host_port_str = rest
        query_params = {}

    # 拆 host:port（支援 IPv6 的 [::1]:443 格式）
    server_address, server_port = _split_host_port(host_port_str)

    # 從 query 取參數（每個值是 list，取第一個）
    def qval(key: str, default: str = "") -> str:
        vals = query_params.get(key, [default])
        return vals[0] if vals else default

    network_type = qval("type", "tcp")
    security_type = qval("security", "none")
    sni_value = qval("sni")
    host_value = qval("host")
    path_value = qval("path")
    flow_value = qval("flow")
    alpn_value = qval("alpn")

    # 判斷 TLS
    is_tls = security_type in ("tls", "reality")

    # ALPN 要拆成列表
    alpn_list = alpn_value.split(",") if alpn_value else None

    return Node(
        name=node_name,
        node_type=NODE_TYPE_VLESS,
        server=server_address,
        port=server_port,
        uuid_str=user_info,
        tls_enabled=is_tls,
        sni=sni_value if sni_value else None,
        alpn=alpn_list,
        host=host_value if host_value else None,
        path=path_value if path_value else None,
        network=network_type,
        flow=flow_value if flow_value else None,
        extra={"security": security_type, "query": query_params},
        raw_dict={"uri": uri},
        source_sub=source_sub,
    )


# ============================================================
# trojan:// 解析
# ============================================================

def parse_trojan_uri(uri: str, source_sub: str = "") -> Node:
    """
    解析 trojan:// 分享鏈。
    格式：trojan://PASSWORD@SERVER:PORT?params#NAME
    """
    without_scheme = uri[len("trojan://"):]

    # 拆 fragment（名稱）
    if "#" in without_scheme:
        main_part, fragment = without_scheme.rsplit("#", 1)
        node_name = urllib.parse.unquote(fragment)
    else:
        main_part = without_scheme
        node_name = "trojan 節點"

    # 拆 password@host:port?query
    at_index = main_part.find("@")
    if at_index < 0:
        raise ValueError("trojan:// 格式錯誤：找不到 '@'")

    password_value = urllib.parse.unquote(main_part[:at_index])
    rest = main_part[at_index + 1:]

    # 拆 query
    if "?" in rest:
        host_port_str, query_str = rest.split("?", 1)
        query_params = urllib.parse.parse_qs(query_str)
    else:
        host_port_str = rest
        query_params = {}

    # 拆 host:port
    server_address, server_port = _split_host_port(host_port_str)

    def qval(key: str, default: str = "") -> str:
        vals = query_params.get(key, [default])
        return vals[0] if vals else default

    sni_value = qval("sni")
    alpn_value = qval("alpn")
    network_type = qval("type", "tcp")
    host_value = qval("host")
    path_value = qval("path")

    alpn_list = alpn_value.split(",") if alpn_value else None

    return Node(
        name=node_name,
        node_type=NODE_TYPE_TROJAN,
        server=server_address,
        port=server_port,
        password=password_value,
        tls_enabled=True,          # trojan 預設就是 TLS
        sni=sni_value if sni_value else None,
        alpn=alpn_list,
        host=host_value if host_value else None,
        path=path_value if path_value else None,
        network=network_type,
        extra={"query": query_params},
        raw_dict={"uri": uri},
        source_sub=source_sub,
    )


# ============================================================
# ss:// 解析（Shadowsocks）
# ============================================================

def parse_ss_uri(uri: str, source_sub: str = "") -> Node:
    """
    解析 ss:// 分享鏈。
    有兩種常見格式：
    格式 A（SIP002）：ss://BASE64(method:password)@SERVER:PORT#NAME
    格式 B（舊式）：  ss://BASE64(method:password@SERVER:PORT)#NAME
    """
    without_scheme = uri[len("ss://"):]

    # 拆 fragment（名稱）
    if "#" in without_scheme:
        main_part, fragment = without_scheme.rsplit("#", 1)
        node_name = urllib.parse.unquote(fragment)
    else:
        main_part = without_scheme
        node_name = "ss 節點"

    # 嘗試判斷是哪種格式
    if "@" in main_part:
        # 格式 A：BASE64部分@SERVER:PORT
        encoded_part, host_port_str = main_part.rsplit("@", 1)
        decoded_user_info = _safe_base64_decode(encoded_part)
        # decoded_user_info 格式：method:password
        if ":" not in decoded_user_info:
            raise ValueError(f"ss:// 格式錯誤：解碼後找不到 'method:password'，得到: '{decoded_user_info[:60]}'")
        method_value, password_value = decoded_user_info.split(":", 1)
    else:
        # 格式 B：整段 base64
        decoded_all = _safe_base64_decode(main_part)
        # 格式：method:password@server:port
        at_index = decoded_all.rfind("@")
        if at_index < 0:
            raise ValueError(f"ss:// 格式錯誤：解碼後找不到 '@'，得到: '{decoded_all[:60]}'")
        user_info_part = decoded_all[:at_index]
        host_port_str = decoded_all[at_index + 1:]
        if ":" not in user_info_part:
            raise ValueError(f"ss:// 格式錯誤：解碼後找不到 'method:password'")
        method_value, password_value = user_info_part.split(":", 1)

    # 去掉 host_port_str 中可能的 query / plugins (例如 /?group=... 或 ?plugin=...)
    if "/?" in host_port_str:
        host_port_str = host_port_str.split("/?", 1)[0]
    elif "?" in host_port_str:
        host_port_str = host_port_str.split("?", 1)[0]
    elif "/" in host_port_str:
        host_port_str = host_port_str.split("/", 1)[0]

    server_address, server_port = _split_host_port(host_port_str)

    return Node(
        name=node_name,
        node_type=NODE_TYPE_SS,
        server=server_address,
        port=server_port,
        password=password_value,
        encryption=method_value.strip(),
        raw_dict={"uri": uri},
        source_sub=source_sub,
    )


# ============================================================
# socks5:// 解析
# ============================================================

def parse_socks5_uri(uri: str, source_sub: str = "") -> Node:
    """
    解析 socks5:// 或 socks:// 分享鏈。
    格式：socks5://[USER:PASS@]SERVER:PORT[#NAME]
    """
    # 統一前綴
    if uri.startswith("socks5://"):
        without_scheme = uri[len("socks5://"):]
    elif uri.startswith("socks://"):
        without_scheme = uri[len("socks://"):]
    else:
        raise ValueError(f"不是 socks5 或 socks 開頭的連結: '{uri[:60]}'")

    # 拆 fragment（名稱）
    if "#" in without_scheme:
        main_part, fragment = without_scheme.rsplit("#", 1)
        node_name = urllib.parse.unquote(fragment)
    else:
        main_part = without_scheme
        node_name = "socks5 節點"

    # 拆 user:pass@host:port
    username_value: str | None = None
    password_value: str | None = None

    if "@" in main_part:
        user_pass_part, host_port_str = main_part.rsplit("@", 1)
        if ":" in user_pass_part:
            # Plain format: user:pass@host:port
            username_value, password_value = user_pass_part.split(":", 1)
            username_value = urllib.parse.unquote(username_value)
            password_value = urllib.parse.unquote(password_value)
        else:
            # V2RayN format: base64(user:pass)@host:port
            try:
                decoded = _safe_base64_decode(user_pass_part)
                if ":" in decoded:
                    username_value, password_value = decoded.split(":", 1)
                else:
                    username_value = decoded
            except ValueError:
                # Not valid base64, treat as plain username
                username_value = urllib.parse.unquote(user_pass_part)
    else:
        host_port_str = main_part

    server_address, server_port = _split_host_port(host_port_str)

    return Node(
        name=node_name,
        node_type=NODE_TYPE_SOCKS5,
        server=server_address,
        port=server_port,
        username=username_value,
        password=password_value,
        raw_dict={"uri": uri},
        source_sub=source_sub,
    )


# ============================================================
# http:// / https:// 代理解析
# ============================================================

def parse_http_uri(uri: str, source_sub: str = "") -> Node:
    """
    解析 http:// 或 https:// 的代理分享鏈。
    格式：http://[USER:PASS@]SERVER:PORT[#NAME]
    """
    # 判斷 TLS
    if uri.startswith("https://"):
        without_scheme = uri[len("https://"):]
        is_tls = True
    else:
        without_scheme = uri[len("http://"):]
        is_tls = False

    # 拆 fragment
    if "#" in without_scheme:
        main_part, fragment = without_scheme.rsplit("#", 1)
        node_name = urllib.parse.unquote(fragment)
    else:
        main_part = without_scheme
        node_name = "http 代理"

    # 拆 user:pass@host:port
    username_value: str | None = None
    password_value: str | None = None

    if "@" in main_part:
        user_pass_part, host_port_str = main_part.rsplit("@", 1)
        if ":" in user_pass_part:
            username_value, password_value = user_pass_part.split(":", 1)
        else:
            username_value = user_pass_part
    else:
        host_port_str = main_part

    server_address, server_port = _split_host_port(host_port_str)

    return Node(
        name=node_name,
        node_type=NODE_TYPE_HTTP,
        server=server_address,
        port=server_port,
        username=username_value,
        password=password_value,
        tls_enabled=is_tls,
        raw_dict={"uri": uri},
        source_sub=source_sub,
    )


# ============================================================
# 通用工具：拆 host:port
# ============================================================

def _split_host_port(host_port_str: str) -> tuple[str, int]:
    """
    把 "host:port" 拆成 (host, port)。
    支援 IPv6 的 "[::1]:443" 格式。
    """
    host_port_str = host_port_str.strip()

    # IPv6 格式：[::1]:443
    if host_port_str.startswith("["):
        bracket_end = host_port_str.find("]")
        if bracket_end < 0:
            raise ValueError(f"IPv6 地址格式錯誤（缺少 ']'）: '{host_port_str}'")
        host_part = host_port_str[1:bracket_end]  # 去掉 [ ]
        rest = host_port_str[bracket_end + 1:]     # 應該是 ":port" 或空
        if rest.startswith(":"):
            port_part = rest[1:]
        else:
            raise ValueError(f"IPv6 地址後面缺少 ':port': '{host_port_str}'")
    else:
        # 普通格式：host:port
        last_colon = host_port_str.rfind(":")
        if last_colon < 0:
            raise ValueError(f"找不到端口號（缺少 ':'）: '{host_port_str}'")
        host_part = host_port_str[:last_colon]
        port_part = host_port_str[last_colon + 1:]

    # 轉換端口號
    port_number = _parse_int_safe(port_part, "port")
    if port_number < 1 or port_number > 65535:
        raise ValueError(f"端口號超出範圍 (1-65535): {port_number}")

    return host_part, port_number


# ============================================================
# 統一入口：根據前綴自動選擇正確的解析函式
# ============================================================

def parse_single_uri(uri_line: str, source_sub: str = "") -> Node:
    """
    自動判斷 URI 類型，呼叫對應的解析函式。
    輸入：一行 URI 字串（例如 "vmess://xxxxx"）
    輸出：一個 Node 物件
    失敗：拋出 ValueError
    """
    uri_line = uri_line.strip()

    if uri_line.startswith("vmess://"):
        return parse_vmess_uri(uri_line, source_sub)
    elif uri_line.startswith("vless://"):
        return parse_vless_uri(uri_line, source_sub)
    elif uri_line.startswith("trojan://"):
        return parse_trojan_uri(uri_line, source_sub)
    elif uri_line.startswith("ss://"):
        return parse_ss_uri(uri_line, source_sub)
    elif uri_line.startswith("socks5://") or uri_line.startswith("socks://"):
        return parse_socks5_uri(uri_line, source_sub)
    elif uri_line.startswith("http://") or uri_line.startswith("https://"):
        return parse_http_uri(uri_line, source_sub)
    else:
        raise ValueError(f"無法辨識的協議前綴: '{uri_line[:60]}'")
