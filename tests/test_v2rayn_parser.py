"""
test_v2rayn_parser.py — 測試 v2rayN 訂閱解析器

用 pytest 跑：
    cd d:\\Codes\\Sing-chain\\Sing-chain
    python -m pytest tests/test_v2rayn_parser.py -v
"""

import base64

import pytest

from parsers.v2rayn_parser import parse_v2rayn_subscription
from parsers.uri_parsers import (
    parse_vmess_uri,
    parse_vless_uri,
    parse_trojan_uri,
    parse_ss_uri,
    parse_socks5_uri,
    parse_http_uri,
    parse_single_uri,
)
from models.node import (
    NODE_TYPE_VMESS,
    NODE_TYPE_VLESS,
    NODE_TYPE_TROJAN,
    NODE_TYPE_SS,
    NODE_TYPE_SOCKS5,
    NODE_TYPE_HTTP,
)


# ============================================================
# 測試用的分享鏈 URI
# ============================================================

# vmess:// 分享鏈範例（base64(JSON)）
def _make_vmess_uri() -> str:
    """
    產生一個合法的 vmess:// 分享鏈。
    vmess:// 後面是 base64 編碼的 JSON。
    """
    import json
    vmess_json = {
        "v": "2",
        "ps": "香港節點",
        "add": "hk.example.com",
        "port": "443",
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": "cdn.example.com",
        "path": "/ws-path",
        "tls": "tls",
        "sni": "hk.example.com",
    }
    json_str = json.dumps(vmess_json)
    encoded = base64.b64encode(json_str.encode()).decode()
    return f"vmess://{encoded}"


SAMPLE_VMESS_URI = _make_vmess_uri()

SAMPLE_VLESS_URI = "vless://aaaaaaaa-1111-2222-3333-444444444444@us.example.com:443?type=ws&security=tls&path=%2Fvless-ws&host=cdn.example.com&sni=us.example.com#美國節點"

SAMPLE_TROJAN_URI = "trojan://my-trojan-password@jp.example.com:443?sni=jp.example.com&alpn=h2,http/1.1#日本Trojan"

# ss:// SIP002 格式：ss://BASE64(method:password)@server:port#name
def _make_ss_uri() -> str:
    user_info = "aes-256-gcm:my-ss-password"
    encoded = base64.b64encode(user_info.encode()).decode()
    return f"ss://{encoded}@sg.example.com:8388#新加坡SS"

SAMPLE_SS_URI = _make_ss_uri()

SAMPLE_SOCKS5_URI = "socks5://user1:pass1@127.0.0.1:1080#本地Socks5"

SAMPLE_HTTP_URI = "http://httpuser:httppass@proxy.example.com:8080#HTTP代理"


# ============================================================
# 單一 URI 解析測試
# ============================================================

class TestUriParsers:
    """個別 URI 解析函式的測試"""

    def test_vmess_parse(self):
        """vmess:// 應該正確解析"""
        node = parse_vmess_uri(SAMPLE_VMESS_URI, "test-sub")
        assert node.node_type == NODE_TYPE_VMESS
        assert node.name == "香港節點"
        assert node.server == "hk.example.com"
        assert node.port == 443
        assert node.uuid_str == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert node.tls_enabled is True
        assert node.network == "ws"
        assert node.path == "/ws-path"

    def test_vless_parse(self):
        """vless:// 應該正確解析（包含 URL encoded 路徑）"""
        node = parse_vless_uri(SAMPLE_VLESS_URI, "test-sub")
        assert node.node_type == NODE_TYPE_VLESS
        assert node.name == "美國節點"
        assert node.server == "us.example.com"
        assert node.port == 443
        assert node.uuid_str == "aaaaaaaa-1111-2222-3333-444444444444"
        assert node.tls_enabled is True
        assert node.network == "ws"
        assert node.path == "/vless-ws"

    def test_trojan_parse(self):
        """trojan:// 應該正確解析"""
        node = parse_trojan_uri(SAMPLE_TROJAN_URI, "test-sub")
        assert node.node_type == NODE_TYPE_TROJAN
        assert node.name == "日本Trojan"
        assert node.server == "jp.example.com"
        assert node.port == 443
        assert node.password == "my-trojan-password"
        assert node.tls_enabled is True
        assert node.alpn == ["h2", "http/1.1"]

    def test_ss_parse(self):
        """ss:// (SIP002) 應該正確解析"""
        node = parse_ss_uri(SAMPLE_SS_URI, "test-sub")
        assert node.node_type == NODE_TYPE_SS
        assert node.name == "新加坡SS"
        assert node.server == "sg.example.com"
        assert node.port == 8388
        assert node.encryption == "aes-256-gcm"
        assert node.password == "my-ss-password"

    def test_socks5_parse(self):
        """socks5:// 應該正確解析"""
        node = parse_socks5_uri(SAMPLE_SOCKS5_URI, "test-sub")
        assert node.node_type == NODE_TYPE_SOCKS5
        assert node.name == "本地Socks5"
        assert node.server == "127.0.0.1"
        assert node.port == 1080
        assert node.username == "user1"
        assert node.password == "pass1"

    def test_http_parse(self):
        """http:// 應該正確解析"""
        node = parse_http_uri(SAMPLE_HTTP_URI, "test-sub")
        assert node.node_type == NODE_TYPE_HTTP
        assert node.name == "HTTP代理"
        assert node.server == "proxy.example.com"
        assert node.port == 8080
        assert node.username == "httpuser"
        assert node.password == "httppass"

    def test_socks5_without_auth(self):
        """socks5:// 沒有帳密也要能解析"""
        node = parse_socks5_uri("socks5://10.0.0.1:9050#NoAuth", "test")
        assert node.node_type == NODE_TYPE_SOCKS5
        assert node.server == "10.0.0.1"
        assert node.port == 9050
        assert node.username is None
        assert node.password is None

    def test_socks_base64_v2rayn_format(self):
        """V2RayN exports socks:// with base64(user:pass)@host:port#name"""
        # base64("blqtblgd:re4b15c72pcq") = "YmxxdGJsZ2Q6cmU0YjE1YzcycGNx"
        uri = "socks://YmxxdGJsZ2Q6cmU0YjE1YzcycGNx@9.142.43.162:5332#US_3"
        node = parse_socks5_uri(uri, "v2rayn-export")
        assert node.node_type == NODE_TYPE_SOCKS5
        assert node.name == "US_3"
        assert node.server == "9.142.43.162"
        assert node.port == 5332
        assert node.username == "blqtblgd"
        assert node.password == "re4b15c72pcq"

    def test_parse_single_uri_auto_dispatch(self):
        """parse_single_uri 應該自動判斷協議並呼叫正確的解析函式"""
        node = parse_single_uri(SAMPLE_SOCKS5_URI, "auto-test")
        assert node.node_type == NODE_TYPE_SOCKS5

        node2 = parse_single_uri(SAMPLE_VLESS_URI, "auto-test")
        assert node2.node_type == NODE_TYPE_VLESS

    def test_unknown_scheme_raises(self):
        """不認識的 URI 前綴應該拋出 ValueError"""
        with pytest.raises(ValueError, match="無法辨識"):
            parse_single_uri("ftp://something", "test")

    def test_vmess_missing_uuid_raises(self):
        """vmess:// 缺少 UUID 應該拋出清楚的錯誤"""
        import json
        bad_json = {"v": "2", "ps": "壞的", "add": "1.2.3.4", "port": "443"}
        encoded = base64.b64encode(json.dumps(bad_json).encode()).decode()
        with pytest.raises(ValueError, match="UUID"):
            parse_vmess_uri(f"vmess://{encoded}")


# ============================================================
# v2rayN 訂閱整體解析測試
# ============================================================

class TestV2raynParser:
    """v2rayN 訂閱解析的測試"""

    def test_parse_plaintext_subscription(self):
        """純文字格式（多行 URI）應該正確解析"""
        lines = "\n".join([
            SAMPLE_VMESS_URI,
            SAMPLE_VLESS_URI,
            SAMPLE_TROJAN_URI,
            SAMPLE_SS_URI,
            SAMPLE_SOCKS5_URI,
        ])
        nodes, errors = parse_v2rayn_subscription(lines, "純文字訂閱")

        assert len(nodes) == 5, f"預期 5 個節點，實際 {len(nodes)}，錯誤: {errors}"
        assert len(errors) == 0

    def test_parse_base64_subscription(self):
        """base64 編碼的訂閱應該自動解碼後解析"""
        lines = "\n".join([
            SAMPLE_VMESS_URI,
            SAMPLE_VLESS_URI,
            SAMPLE_SOCKS5_URI,
        ])
        # 把整段文字做 base64 編碼
        encoded_text = base64.b64encode(lines.encode()).decode()

        nodes, errors = parse_v2rayn_subscription(encoded_text, "base64訂閱")

        assert len(nodes) == 3, f"預期 3 個節點，實際 {len(nodes)}，錯誤: {errors}"
        assert len(errors) == 0

    def test_empty_input(self):
        """空輸入應該回報「沒有找到」的錯誤"""
        nodes, errors = parse_v2rayn_subscription("", "空訂閱")
        assert len(nodes) == 0
        assert len(errors) >= 1
        assert "沒有找到" in errors[0]

    def test_mixed_valid_and_invalid_lines(self):
        """混合合法和不合法的行，合法的要解析成功，不合法的要回報錯誤"""
        lines = "\n".join([
            SAMPLE_VLESS_URI,
            "vmess://not_valid_base64_!!!",
            SAMPLE_SOCKS5_URI,
        ])
        nodes, errors = parse_v2rayn_subscription(lines, "混合訂閱")

        # 合法的 2 個應該成功
        assert len(nodes) == 2
        # 壞的 1 個應該有錯誤
        assert len(errors) == 1
        # 錯誤訊息要有行號
        assert "2" in errors[0]  # 第 2 行

    def test_skip_blank_lines(self):
        """空行應該被跳過，不算錯誤"""
        lines = f"\n\n{SAMPLE_SOCKS5_URI}\n\n"
        nodes, errors = parse_v2rayn_subscription(lines, "有空行")
        assert len(nodes) == 1
        assert len(errors) == 0
