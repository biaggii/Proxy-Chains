"""
port_mapping.py — 端口映射（PortMapping）的資料結構

一個「PortMapping」就是：
  在本地開一個端口（listen_host:listen_port），
  所有連到這個端口的流量，都走指定的 chain 出去。

每個瀏覽器 profile 會設不同的本地代理端口，
每個端口對應不同的 chain（= 不同的出口 IP）。
"""

import uuid


def make_mapping_id() -> str:
    """產生一個不重複的端口映射 ID"""
    return uuid.uuid4().hex[:8]


class PortMapping:
    """
    一個端口映射的完整資料。

    欄位說明：
    - mapping_id   : 唯一識別碼
    - listen_host  : 監聽地址，通常是 "127.0.0.1"
    - listen_port  : 監聽端口號，例如 20001
    - chain_id     : 綁定的 chain ID（流量走哪條鏈出去）
    - remark       : 備註，例如 "Applicaition Profile #1"
    """

    def __init__(
        self,
        listen_port: int,
        chain_id: str,
        listen_host: str = "127.0.0.1",
        mapping_id: str | None = None,
        remark: str = "",
    ):
        self.mapping_id: str = mapping_id if mapping_id else make_mapping_id()
        self.listen_host: str = listen_host
        self.listen_port: int = listen_port
        self.chain_id: str = chain_id
        self.remark: str = remark

    def proxy_address(self) -> str:
        """回傳給 Client 用的代理地址字串：host:port"""
        return f"{self.listen_host}:{self.listen_port}"

    # ---------- 序列化 ----------

    def to_dict(self) -> dict:
        """轉成 dict"""
        return {
            "mapping_id": self.mapping_id,
            "listen_host": self.listen_host,
            "listen_port": self.listen_port,
            "chain_id": self.chain_id,
            "remark": self.remark,
        }

    @staticmethod
    def from_dict(data: dict) -> "PortMapping":
        """從 dict 還原"""
        return PortMapping(
            mapping_id=data.get("mapping_id"),
            listen_host=data.get("listen_host", "127.0.0.1"),
            listen_port=int(data.get("listen_port", 0)),
            chain_id=data.get("chain_id", ""),
            remark=data.get("remark", ""),
        )

    def __repr__(self) -> str:
        return (
            f"PortMapping({self.mapping_id}, "
            f"{self.listen_host}:{self.listen_port} -> chain={self.chain_id})"
        )
