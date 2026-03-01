"""
node.py — 節點（Node）的資料結構

一個「節點」就是一條代理伺服器的完整資訊。
例如：一台 vmess 伺服器、一個 socks5 伺服器、一個 trojan 伺服器……
不管來源是機場訂閱還是手動輸入，最後都變成同一種 Node。
"""

import uuid


# ============================================================
# 所有支援的節點類型，用字串常數定義，避免打錯字
# ============================================================
NODE_TYPE_VMESS = "vmess"
NODE_TYPE_VLESS = "vless"
NODE_TYPE_TROJAN = "trojan"
NODE_TYPE_SS = "shadowsocks"       # Shadowsocks
NODE_TYPE_WG = "wireguard"         # WireGuard
NODE_TYPE_SOCKS5 = "socks5"
NODE_TYPE_HTTP = "http"
NODE_TYPE_UNKNOWN = "unknown"

# 把所有合法類型放在一個清單裡，方便做檢查
ALL_NODE_TYPES: list[str] = [
    NODE_TYPE_VMESS,
    NODE_TYPE_VLESS,
    NODE_TYPE_TROJAN,
    NODE_TYPE_SS,
    NODE_TYPE_WG,
    NODE_TYPE_SOCKS5,
    NODE_TYPE_HTTP,
    NODE_TYPE_UNKNOWN,
]


def make_node_id() -> str:
    """產生一個不重複的節點 ID（用 UUID4，短一點取前 8 碼就夠）"""
    return uuid.uuid4().hex[:8]


class Node:
    """
    一個代理節點的完整資料。

    欄位說明：
    - node_id     : 唯一識別碼（自動產生）
    - name        : 顯示名稱，例如 "香港-01"
    - node_type   : 節點類型，例如 "vmess", "socks5"
    - server      : 伺服器地址，例如 "1.2.3.4" 或 "hk.example.com"
    - port        : 伺服器端口號
    - username    : 使用者名稱（socks5/http 可能會用到，其他可空）
    - password    : 密碼（socks5/http/trojan 會用到）
    - uuid_str    : UUID（vmess/vless 用）
    - tls_enabled : 是否啟用 TLS
    - sni         : TLS 的 Server Name Indication
    - alpn        : TLS 的 ALPN 列表，例如 ["h2", "http/1.1"]
    - path        : WebSocket 或 HTTP/2 的路徑
    - host        : HTTP 偽裝的 Host 頭
    - network     : 傳輸方式，例如 "tcp", "ws", "grpc", "h2"
    - extra       : 其他額外參數（dict），存放不常用的欄位
    - raw_dict    : 原始解析資料（完整保留，方便 debug）
    - source_sub  : 這個節點來自哪個訂閱（訂閱名稱）
    - encryption  : 加密方式（ss 用，例如 "aes-256-gcm"）
    - alter_id    : AlterID（vmess 用）
    - security    : vmess 安全性設定（例如 "auto"）
    - flow        : VLESS 的 flow 設定（例如 "xtls-rprx-vision"）
    - wg_public_key    : WireGuard 伺服器公鑰
    - wg_private_key   : WireGuard 客戶端私鑰
    - wg_local_address : WireGuard 本地 IP
    """

    def __init__(
        self,
        name: str,
        node_type: str,
        server: str,
        port: int,
        node_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
        uuid_str: str | None = None,
        tls_enabled: bool = False,
        sni: str | None = None,
        alpn: list[str | None] = None,
        path: str | None = None,
        host: str | None = None,
        network: str = "tcp",
        extra: dict | None = None,
        raw_dict: dict | None = None,
        source_sub: str = "",
        encryption: str | None = None,
        alter_id: int = 0,
        security: str | None = None,
        flow: str | None = None,
        wg_public_key: str | None = None,
        wg_private_key: str | None = None,
        wg_local_address: str | None = None,
    ):
        # ---------- 基本欄位 ----------
        # 如果沒給 node_id，就自動產生一個
        self.node_id: str = node_id if node_id else make_node_id()
        self.name: str = name
        self.node_type: str = node_type
        self.server: str = server
        self.port: int = port

        # ---------- 認證欄位 ----------
        self.username: str | None = username
        self.password: str | None = password
        self.uuid_str: str | None = uuid_str

        # ---------- TLS 欄位 ----------
        self.tls_enabled: bool = tls_enabled
        self.sni: str | None = sni
        self.alpn: list[str | None] = alpn

        # ---------- 傳輸欄位 ----------
        self.path: str | None = path
        self.host: str | None = host
        self.network: str = network

        # ---------- 協議特殊欄位 ----------
        self.encryption: str | None = encryption    # ss 加密方式
        self.alter_id: int = alter_id                  # vmess alterID
        self.security: str | None = security        # vmess 安全性
        self.flow: str | None = flow                # vless flow
        self.wg_public_key: str | None = wg_public_key
        self.wg_private_key: str | None = wg_private_key
        self.wg_local_address: str | None = wg_local_address

        # ---------- 其他 ----------
        self.extra: dict = extra if extra else {}
        self.raw_dict: dict = raw_dict if raw_dict else {}
        self.source_sub: str = source_sub

    def to_dict(self) -> dict:
        """把 Node 轉成 dict，方便存成 JSON"""
        return {
            "node_id": self.node_id,
            "name": self.name,
            "node_type": self.node_type,
            "server": self.server,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "uuid_str": self.uuid_str,
            "tls_enabled": self.tls_enabled,
            "sni": self.sni,
            "alpn": self.alpn,
            "path": self.path,
            "host": self.host,
            "network": self.network,
            "encryption": self.encryption,
            "alter_id": self.alter_id,
            "security": self.security,
            "flow": self.flow,
            "wg_public_key": self.wg_public_key,
            "wg_private_key": self.wg_private_key,
            "wg_local_address": self.wg_local_address,
            "extra": self.extra,
            "raw_dict": self.raw_dict,
            "source_sub": self.source_sub,
        }

    @staticmethod
    def from_dict(data: dict) -> "Node":
        """從 dict 還原 Node（從 JSON 讀回來用的）"""
        return Node(
            node_id=data.get("node_id"),
            name=data.get("name", "未命名"),
            node_type=data.get("node_type", NODE_TYPE_UNKNOWN),
            server=data.get("server", ""),
            port=int(data.get("port", 0)),
            username=data.get("username"),
            password=data.get("password"),
            uuid_str=data.get("uuid_str"),
            tls_enabled=bool(data.get("tls_enabled", False)),
            sni=data.get("sni"),
            alpn=data.get("alpn"),
            path=data.get("path"),
            host=data.get("host"),
            network=data.get("network", "tcp"),
            encryption=data.get("encryption"),
            alter_id=int(data.get("alter_id", 0)),
            security=data.get("security"),
            flow=data.get("flow"),
            wg_public_key=data.get("wg_public_key"),
            wg_private_key=data.get("wg_private_key"),
            wg_local_address=data.get("wg_local_address"),
            extra=data.get("extra", {}),
            raw_dict=data.get("raw_dict", {}),
            source_sub=data.get("source_sub", ""),
        )

    def __repr__(self) -> str:
        """印出來方便 debug"""
        return f"Node({self.node_id}, {self.name}, {self.node_type}, {self.server}:{self.port})"
