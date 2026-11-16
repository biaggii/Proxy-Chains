"""
subscription.py — 訂閱（Subscription）的資料結構

一個「訂閱」就是一個遠端 URL，裡面包含很多代理節點。
使用者可以新增多個訂閱，每個訂閱有名字、URL、類型。
"""



# ============================================================
# 訂閱類型常數
# ============================================================
SUB_TYPE_CLASH = "clash"          # Clash YAML 格式
SUB_TYPE_V2RAYN = "v2rayn"       # v2rayN 格式（base64 或純文字分享鏈）
SUB_TYPE_AUTO = "auto"           # 自動偵測

ALL_SUB_TYPES: list[str] = [SUB_TYPE_CLASH, SUB_TYPE_V2RAYN, SUB_TYPE_AUTO]


class Subscription:
    """
    一個訂閱的完整資料。

    欄位說明：
    - sub_id       : 唯一識別碼
    - name         : 顯示名稱，例如 "主力機場"
    - url          : 訂閱的下載網址
    - sub_type     : 訂閱類型 (clash / v2rayn / auto)
    - last_update  : 上次更新時間（ISO 格式字串，可空）
    - node_count   : 上次解析出的節點數量
    - raw_text     : 上次下載的原始文字（方便重新解析，可空）
    """

    def __init__(
        self,
        name: str,
        url: str,
        sub_type: str = SUB_TYPE_AUTO,
        sub_id: str | None = None,
        last_update: str | None = None,
        node_count: int = 0,
        raw_text: str | None = None,
        enable_update: bool = True,
        update_interval: int = 0,
        remarks_filter: str = "",
        convert_target_type: str = "auto",
        user_agent: str = "",
        http_headers: dict | None = None,
        sort: int = 0,
        previous_proxy_remarks: str = "",
        next_proxy_remarks: str = "",
        custom_config_core: str = "",
        custom_config_socks_port: int = 0,
        remarks_memo: str = "",
    ):
        # 如果沒給 sub_id，用簡單方式產生
        import uuid
        self.sub_id: str = sub_id if sub_id else uuid.uuid4().hex[:8]
        self.name: str = name
        self.url: str = url
        self.sub_type: str = sub_type
        self.last_update: str | None = last_update
        self.node_count: int = node_count
        self.raw_text: str | None = raw_text
        self.enable_update = bool(enable_update)
        self.update_interval = max(0, int(update_interval or 0))
        self.remarks_filter = remarks_filter or ""
        self.convert_target_type = convert_target_type or "auto"
        self.user_agent = user_agent or ""
        self.http_headers = dict(http_headers or {})
        self.sort = int(sort or 0)
        self.previous_proxy_remarks = previous_proxy_remarks or ""
        self.next_proxy_remarks = next_proxy_remarks or ""
        self.custom_config_core = custom_config_core or ""
        self.custom_config_socks_port = int(custom_config_socks_port or 0)
        self.remarks_memo = remarks_memo or ""

    def to_dict(self) -> dict:
        """轉成 dict，方便存成 JSON"""
        return {
            "sub_id": self.sub_id,
            "name": self.name,
            "url": self.url,
            "sub_type": self.sub_type,
            "last_update": self.last_update,
            "node_count": self.node_count,
            "enable_update": self.enable_update,
            "update_interval": self.update_interval,
            "remarks_filter": self.remarks_filter,
            "convert_target_type": self.convert_target_type,
            "user_agent": self.user_agent,
            "http_headers": self.http_headers,
            "sort": self.sort,
            "previous_proxy_remarks": self.previous_proxy_remarks,
            "next_proxy_remarks": self.next_proxy_remarks,
            "custom_config_core": self.custom_config_core,
            "custom_config_socks_port": self.custom_config_socks_port,
            "remarks_memo": self.remarks_memo,
            # raw_text 不存進 state.json（太大了），
            # 需要的話另外存檔案
        }

    @staticmethod
    def from_dict(data: dict) -> "Subscription":
        """從 dict 還原"""
        return Subscription(
            sub_id=data.get("sub_id"),
            name=data.get("name", "未命名訂閱"),
            url=data.get("url", ""),
            sub_type=data.get("sub_type", SUB_TYPE_AUTO),
            last_update=data.get("last_update"),
            node_count=int(data.get("node_count", 0)),
            enable_update=data.get("enable_update", True),
            update_interval=data.get("update_interval", data.get("auto_update_interval", 0)),
            remarks_filter=data.get("remarks_filter", ""),
            convert_target_type=data.get("convert_target_type", "auto"),
            user_agent=data.get("user_agent", ""),
            http_headers=data.get("http_headers", {}),
            sort=data.get("sort", 0),
            previous_proxy_remarks=data.get("previous_proxy_remarks", ""),
            next_proxy_remarks=data.get("next_proxy_remarks", ""),
            custom_config_core=data.get("custom_config_core", ""),
            custom_config_socks_port=data.get("custom_config_socks_port", 0),
            remarks_memo=data.get("remarks_memo", ""),
        )

    def __repr__(self) -> str:
        return f"Subscription({self.sub_id}, {self.name}, {self.sub_type})"
