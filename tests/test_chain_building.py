"""
test_chain_building.py — 測試鏈式代理的建構邏輯

這個測試檔目前先驗證 Node 和 Chain 的基本操作。
CoreAdapter 的 generate_config 測試會在第 3 批加入。

用 pytest 跑：
    cd d:\\Codes\\Sing-chain\\Sing-chain
    python -m pytest tests/test_chain_building.py -v
"""

import pytest

from models.node import Node, NODE_TYPE_VMESS, NODE_TYPE_SOCKS5, NODE_TYPE_TROJAN


# ============================================================
# Node 基本操作測試
# ============================================================

class TestNodeBasics:
    """Node 模型的基本功能測試"""

    def test_create_node(self):
        """應該能正常建立一個 Node"""
        node = Node(
            name="測試節點",
            node_type=NODE_TYPE_VMESS,
            server="1.2.3.4",
            port=443,
            uuid_str="test-uuid",
        )
        assert node.name == "測試節點"
        assert node.server == "1.2.3.4"
        assert node.port == 443
        assert node.node_id is not None  # 應該自動產生

    def test_node_id_auto_generated(self):
        """兩個 Node 的 node_id 應該不同"""
        node_a = Node(name="A", node_type=NODE_TYPE_VMESS, server="a.com", port=443)
        node_b = Node(name="B", node_type=NODE_TYPE_VMESS, server="b.com", port=443)
        assert node_a.node_id != node_b.node_id

    def test_node_to_dict_and_back(self):
        """Node -> dict -> Node 來回不應該丟失資料"""
        original = Node(
            name="完整測試",
            node_type=NODE_TYPE_TROJAN,
            server="trojan.example.com",
            port=443,
            password="secret",
            tls_enabled=True,
            sni="trojan.example.com",
            alpn=["h2", "http/1.1"],
            network="tcp",
        )
        d = original.to_dict()
        restored = Node.from_dict(d)

        assert restored.name == original.name
        assert restored.node_type == original.node_type
        assert restored.server == original.server
        assert restored.port == original.port
        assert restored.password == original.password
        assert restored.tls_enabled == original.tls_enabled
        assert restored.sni == original.sni
        assert restored.alpn == original.alpn

    def test_node_repr(self):
        """__repr__ 應該回傳可讀的字串"""
        node = Node(name="HK-01", node_type=NODE_TYPE_VMESS, server="hk.com", port=443)
        repr_str = repr(node)
        assert "HK-01" in repr_str
        assert "vmess" in repr_str


# ============================================================
# 鏈式代理建構測試（純資料面）
# ============================================================

class TestChainBuilding:
    """
    測試鏈式代理的建構邏輯。
    這裡只測「資料面」的正確性，不測 config 生成。
    """

    def test_chain_hop_order(self):
        """
        驗證 chain hops 的順序邏輯：
        chain = [A, B, C] 表示流量走 本地 -> A -> B -> C -> 目標
        在 sing-box 中，最後的 outbound 是 C（detour=B），B（detour=A），A（直連）
        """
        # 建立三個節點
        node_a = Node(name="Hop1-HK", node_type=NODE_TYPE_VMESS, server="a.com", port=443)
        node_b = Node(name="Hop2-JP", node_type=NODE_TYPE_TROJAN, server="b.com", port=443)
        node_c = Node(name="Hop3-Socks5", node_type=NODE_TYPE_SOCKS5, server="c.com", port=1080)

        # 模擬一條 chain 的 hop list
        chain_hops: list[Node] = [node_a, node_b, node_c]

        # 驗證順序
        assert chain_hops[0].name == "Hop1-HK"     # 第一跳
        assert chain_hops[1].name == "Hop2-JP"     # 第二跳
        assert chain_hops[2].name == "Hop3-Socks5" # 落地

    def test_wrap_socks5_creates_new_chain(self):
        """
        驗證 Wrap Socks5 功能：
        pre_chain = [A, B]
        socks5_node = C
        new_chain = [A, B, C]
        """
        # Pre-chain 的節點
        hop1 = Node(name="機場A", node_type=NODE_TYPE_VMESS, server="a.com", port=443)
        hop2 = Node(name="機場B", node_type=NODE_TYPE_TROJAN, server="b.com", port=443)
        pre_chain_hops = [hop1, hop2]

        # 自訂落地 socks5
        landing_socks5 = Node(
            name="落地Socks5",
            node_type=NODE_TYPE_SOCKS5,
            server="landing.example.com",
            port=1080,
            username="user",
            password="pass",
        )

        # Wrap：把 pre-chain 加上 socks5 = 新 chain
        new_chain_hops = pre_chain_hops + [landing_socks5]

        # 驗證
        assert len(new_chain_hops) == 3
        assert new_chain_hops[0].name == "機場A"
        assert new_chain_hops[1].name == "機場B"
        assert new_chain_hops[2].name == "落地Socks5"
        assert new_chain_hops[2].node_type == NODE_TYPE_SOCKS5

    def test_single_hop_chain(self):
        """只有一跳的 chain 也應該正常運作"""
        single_node = Node(
            name="直連Socks5",
            node_type=NODE_TYPE_SOCKS5,
            server="10.0.0.1",
            port=9050,
        )
        chain_hops = [single_node]
        assert len(chain_hops) == 1
        assert chain_hops[0].server == "10.0.0.1"

    def test_chain_with_detour_tags(self):
        """
        模擬 sing-box 的 detour tag 生成邏輯：
        chain_id = "c1"
        hops = [A, B, C]
        生成：
          CHAIN_c1_H1 = A (無 detour)
          CHAIN_c1_H2 = B (detour = CHAIN_c1_H1)
          CHAIN_c1_H3 = C (detour = CHAIN_c1_H2)
        """
        chain_id = "c1"
        hops = [
            Node(name="A", node_type=NODE_TYPE_VMESS, server="a.com", port=443),
            Node(name="B", node_type=NODE_TYPE_TROJAN, server="b.com", port=443),
            Node(name="C", node_type=NODE_TYPE_SOCKS5, server="c.com", port=1080),
        ]

        # 模擬生成 tag 和 detour 的邏輯
        generated_outbounds: list[dict] = []

        for hop_index, hop_node in enumerate(hops):
            hop_number = hop_index + 1
            tag = f"CHAIN_{chain_id}_H{hop_number}"

            outbound_dict: dict = {
                "tag": tag,
                "type": hop_node.node_type,
                "server": hop_node.server,
                "server_port": hop_node.port,
            }

            # 第 2 跳開始要加 detour（指向上一跳的 tag）
            if hop_index > 0:
                previous_tag = f"CHAIN_{chain_id}_H{hop_number - 1}"
                outbound_dict["detour"] = previous_tag

            generated_outbounds.append(outbound_dict)

        # 驗證
        assert len(generated_outbounds) == 3

        # 第一跳沒有 detour
        assert "detour" not in generated_outbounds[0]
        assert generated_outbounds[0]["tag"] == "CHAIN_c1_H1"

        # 第二跳 detour 指向第一跳
        assert generated_outbounds[1]["detour"] == "CHAIN_c1_H1"
        assert generated_outbounds[1]["tag"] == "CHAIN_c1_H2"

        # 第三跳 detour 指向第二跳
        assert generated_outbounds[2]["detour"] == "CHAIN_c1_H2"
        assert generated_outbounds[2]["tag"] == "CHAIN_c1_H3"

    def test_multiple_chains_independent(self):
        """多條 chain 的 tag 不應該互相衝突"""
        chain_ids = ["c1", "c2", "c3"]
        all_tags: list[str] = []

        for cid in chain_ids:
            for hop_num in range(1, 4):
                tag = f"CHAIN_{cid}_H{hop_num}"
                all_tags.append(tag)

        # 所有 tag 應該都不重複
        assert len(all_tags) == len(set(all_tags))
