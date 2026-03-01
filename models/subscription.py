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

    def to_dict(self) -> dict:
        """轉成 dict，方便存成 JSON"""
        return {
            "sub_id": self.sub_id,
            "name": self.name,
            "url": self.url,
            "sub_type": self.sub_type,
            "last_update": self.last_update,
            "node_count": self.node_count,
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
        )

    def __repr__(self) -> str:
        return f"Subscription({self.sub_id}, {self.name}, {self.sub_type})"
