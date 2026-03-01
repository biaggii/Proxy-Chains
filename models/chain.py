"""
chain.py — 鏈式代理（Chain）的資料結構

一條「Chain」就是一組代理節點的有序組合，
流量依序經過每個 hop：Hop1 -> Hop2 -> Hop3 -> ... -> 目標

例如：
  chain hops = [機場HK, 機場JP, 落地Socks5]
  流量路徑 = 本地 -> 機場HK -> 機場JP -> 落地Socks5 -> 目標網站

每個 hop 用 node_id 來引用 Node 物件。
"""

import uuid


def make_chain_id() -> str:
    """產生一個不重複的 Chain ID（取前 8 碼就夠識別）"""
    return uuid.uuid4().hex[:8]


class Chain:
    """
    一條鏈式代理的完整資料。

    欄位說明：
    - chain_id      : 唯一識別碼
    - name          : 顯示名稱，例如 "HK->JP->落地"
    - hop_node_ids  : 有序的 node_id 清單，第 0 個是第一跳
    """

    def __init__(
        self,
        name: str,
        hop_node_ids: list[str | None] = None,
        chain_id: str | None = None,
    ):
        # 如果沒給 chain_id，就自動產生一個
        self.chain_id: str = chain_id if chain_id else make_chain_id()
        self.name: str = name
        # hop_node_ids 是一個 list，裡面放 node_id 字串
        self.hop_node_ids: list[str] = hop_node_ids if hop_node_ids else []

    # ---------- 操作 hops 的方法 ----------

    def add_hop(self, node_id: str) -> None:
        """在最後面加一個 hop"""
        self.hop_node_ids.append(node_id)

    def remove_hop(self, index: int) -> None:
        """移除指定位置的 hop"""
        if 0 <= index < len(self.hop_node_ids):
            self.hop_node_ids.pop(index)

    def move_hop_up(self, index: int) -> None:
        """把某個 hop 往上移一格"""
        if index > 0 and index < len(self.hop_node_ids):
            # 跟上面的交換
            self.hop_node_ids[index], self.hop_node_ids[index - 1] = (
                self.hop_node_ids[index - 1],
                self.hop_node_ids[index],
            )

    def move_hop_down(self, index: int) -> None:
        """把某個 hop 往下移一格"""
        if index >= 0 and index < len(self.hop_node_ids) - 1:
            # 跟下面的交換
            self.hop_node_ids[index], self.hop_node_ids[index + 1] = (
                self.hop_node_ids[index + 1],
                self.hop_node_ids[index],
            )

    def hop_count(self) -> int:
        """回傳這條 chain 有幾跳"""
        return len(self.hop_node_ids)

    # ---------- 序列化 ----------

    def to_dict(self) -> dict:
        """轉成 dict，方便存成 JSON"""
        return {
            "chain_id": self.chain_id,
            "name": self.name,
            "hop_node_ids": self.hop_node_ids,
        }

    @staticmethod
    def from_dict(data: dict) -> "Chain":
        """從 dict 還原"""
        return Chain(
            chain_id=data.get("chain_id"),
            name=data.get("name", "未命名鏈"),
            hop_node_ids=data.get("hop_node_ids", []),
        )

    def __repr__(self) -> str:
        hops_str = " -> ".join(self.hop_node_ids[:5])
        if len(self.hop_node_ids) > 5:
            hops_str += " -> ..."
        return f"Chain({self.chain_id}, {self.name}, [{hops_str}])"
