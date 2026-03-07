"""
test_clash_parser.py — 測試 Clash YAML 解析器

用 pytest 跑：
    cd d:\\Codes\\Sing-chain\\Sing-chain
    python -m pytest tests/test_clash_parser.py -v
"""

import pytest

from parsers.clash_yaml_parser import parse_clash_yaml
from models.node import NODE_TYPE_VMESS, NODE_TYPE_TROJAN, NODE_TYPE_SS, NODE_TYPE_SOCKS5


# ============================================================
# 測試用的 YAML 文字
# ============================================================

# 正常的 Clash YAML，包含多種節點類型
SAMPLE_CLASH_YAML = """
port: 7890
socks-port: 7891
mode: rule

proxies:
  - name: "香港-01-vmess"
    type: vmess
    server: hk1.example.com
    port: 443
    uuid: aaaaaaaa-1111-2222-3333-444444444444
    alterId: 0
    cipher: auto
    tls: true
    network: ws
    ws-opts:
      path: /chat
      headers:
        Host: cdn.example.com

  - name: "日本-01-trojan"
    type: trojan
    server: jp1.example.com
    port: 443
    password: my-trojan-password
    sni: jp1.example.com
    skip-cert-verify: false

  - name: "新加坡-01-ss"
    type: ss
    server: sg1.example.com
    port: 8388
    cipher: aes-256-gcm
    password: my-ss-password

  - name: "本地-socks5"
    type: socks5
    server: 127.0.0.1
    port: 1080
    username: user1
    password: pass1
"""

# 空的 proxies
SAMPLE_EMPTY_PROXIES = """
port: 7890
proxies: []
"""

# 沒有 proxies key
SAMPLE_NO_PROXIES_KEY = """
port: 7890
rules:
  - MATCH,DIRECT
"""

# 損壞的 YAML
SAMPLE_BAD_YAML = """
port: 7890
proxies:
  - name: "壞的節點
    type: vmess
    [[[invalid yaml here
"""


# ============================================================
# 測試案例
# ============================================================

class TestClashYamlParser:
    """Clash YAML 解析器的測試"""

    def test_parse_normal_yaml(self):
        """正常 YAML 應該解析出 4 個節點"""
        nodes, errors = parse_clash_yaml(SAMPLE_CLASH_YAML, "測試訂閱")

        # 應該有 4 個節點
        assert len(nodes) == 4, f"預期 4 個節點，實際 {len(nodes)}"
        # 不應該有錯誤
        assert len(errors) == 0, f"不應該有錯誤，但有: {errors}"

    def test_vmess_node_fields(self):
        """vmess 節點的欄位應該正確"""
        nodes, _ = parse_clash_yaml(SAMPLE_CLASH_YAML, "測試")

        vmess_node = nodes[0]
        assert vmess_node.name == "香港-01-vmess"
        assert vmess_node.node_type == NODE_TYPE_VMESS
        assert vmess_node.server == "hk1.example.com"
        assert vmess_node.port == 443
        assert vmess_node.uuid_str == "aaaaaaaa-1111-2222-3333-444444444444"
        assert vmess_node.tls_enabled is True
        assert vmess_node.network == "ws"
        assert vmess_node.path == "/chat"
        assert vmess_node.host == "cdn.example.com"

    def test_trojan_node_fields(self):
        """trojan 節點的欄位應該正確"""
        nodes, _ = parse_clash_yaml(SAMPLE_CLASH_YAML, "測試")

        trojan_node = nodes[1]
        assert trojan_node.name == "日本-01-trojan"
        assert trojan_node.node_type == NODE_TYPE_TROJAN
        assert trojan_node.password == "my-trojan-password"
        assert trojan_node.sni == "jp1.example.com"

    def test_ss_node_fields(self):
        """shadowsocks 節點的欄位應該正確"""
        nodes, _ = parse_clash_yaml(SAMPLE_CLASH_YAML, "測試")

        ss_node = nodes[2]
        assert ss_node.name == "新加坡-01-ss"
        assert ss_node.node_type == NODE_TYPE_SS
        assert ss_node.encryption == "aes-256-gcm"
        assert ss_node.password == "my-ss-password"

    def test_socks5_node_fields(self):
        """socks5 節點的欄位應該正確"""
        nodes, _ = parse_clash_yaml(SAMPLE_CLASH_YAML, "測試")

        socks5_node = nodes[3]
        assert socks5_node.name == "本地-socks5"
        assert socks5_node.node_type == NODE_TYPE_SOCKS5
        assert socks5_node.server == "127.0.0.1"
        assert socks5_node.port == 1080
        assert socks5_node.username == "user1"
        assert socks5_node.password == "pass1"

    def test_source_sub_name(self):
        """每個節點的 source_sub 應該是傳入的訂閱名稱"""
        nodes, _ = parse_clash_yaml(SAMPLE_CLASH_YAML, "我的機場")
        for node in nodes:
            assert node.source_sub == "我的機場"

    def test_empty_proxies(self):
        """空的 proxies 清單應該回報錯誤"""
        nodes, errors = parse_clash_yaml(SAMPLE_EMPTY_PROXIES, "空訂閱")
        assert len(nodes) == 0
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_no_proxies_key(self):
        """沒有 proxies key 應該回報錯誤"""
        nodes, errors = parse_clash_yaml(SAMPLE_NO_PROXIES_KEY, "缺key")
        assert len(nodes) == 0
        assert len(errors) == 1
        assert "proxies" in errors[0]

    def test_bad_yaml(self):
        """損壞的 YAML 應該回報解析錯誤"""
        nodes, errors = parse_clash_yaml(SAMPLE_BAD_YAML, "壞的")
        assert len(nodes) == 0
        assert len(errors) >= 1

    def test_node_has_raw_dict(self):
        """每個節點都應該保留原始 dict（方便 debug）"""
        nodes, _ = parse_clash_yaml(SAMPLE_CLASH_YAML, "測試")
        for node in nodes:
            assert isinstance(node.raw_dict, dict)
            assert len(node.raw_dict) > 0

    def test_node_to_dict_roundtrip(self):
        """Node -> dict -> Node 來回轉換不能丟資料"""
        nodes, _ = parse_clash_yaml(SAMPLE_CLASH_YAML, "測試")
        from models.node import Node

        for original_node in nodes:
            d = original_node.to_dict()
            restored_node = Node.from_dict(d)
            assert restored_node.name == original_node.name
            assert restored_node.node_type == original_node.node_type
            assert restored_node.server == original_node.server
            assert restored_node.port == original_node.port
