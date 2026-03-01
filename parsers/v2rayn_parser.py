"""
v2rayn_parser.py — 解析 v2rayN 訂閱（base64 或純文字分享鏈）

v2rayN 訂閱的格式有兩種可能：
1. 整段 base64 編碼 → 解碼後得到多行文字，每行一個分享鏈
2. 純文字 → 每行一個分享鏈

每行可能是 vmess://、vless://、trojan://、ss://、socks5://、http:// 開頭的 URI。

這個模組做的事情：
1. 判斷內容是不是 base64 編碼
2. 拆成多行
3. 每行呼叫 uri_parsers.parse_single_uri 來解析
4. 成功的放進 node_list，失敗的放進 error_list（帶行號和原因）
"""

import base64

from models.node import Node
from parsers.uri_parsers import parse_single_uri


# ============================================================
# 已知的合法 URI 前綴，用來判斷是不是純文字格式
# ============================================================
KNOWN_URI_PREFIXES: list[str] = [
    "vmess://",
    "vless://",
    "trojan://",
    "ss://",
    "socks5://",
    "socks://",
    "http://",
    "https://",
]


def parse_v2rayn_subscription(
    raw_text: str,
    source_sub_name: str = "",
) -> tuple[list[Node], list[str]]:
    """
    解析 v2rayN 訂閱文字。

    參數：
    - raw_text        : 下載回來的原始文字
    - source_sub_name : 來源訂閱名稱

    回傳值：
    - (成功的節點清單, 錯誤訊息清單)
    """
    # --- 第 1 步：判斷是 base64 還是純文字 ---
    decoded_text = _try_decode_base64(raw_text)

    # --- 第 2 步：拆成多行 ---
    all_lines = decoded_text.splitlines()

    # --- 第 3 步：逐行解析 ---
    good_nodes: list[Node] = []
    error_messages: list[str] = []

    for line_number, line_text in enumerate(all_lines, start=1):
        # 去掉前後空白
        line_text = line_text.strip()

        # 跳過空行
        if not line_text:
            continue

        # 跳過明顯不是 URI 的行（例如註解）
        if not _looks_like_uri(line_text):
            # 不算錯誤，只是跳過（可能是訂閱資訊行）
            continue

        # 嘗試解析這一行
        try:
            node = parse_single_uri(line_text, source_sub=source_sub_name)
            good_nodes.append(node)
        except Exception as err:
            # 記下錯誤：行號 + 前 60 字 + 原因
            preview = line_text[:60]
            error_messages.append(
                f"第 {line_number} 行解析失敗: '{preview}...' → 原因: {err}"
            )

    # --- 第 4 步：如果完全沒有節點，額外提示 ---
    if len(good_nodes) == 0 and len(error_messages) == 0:
        error_messages.append(
            f"訂閱 '{source_sub_name}' 完全沒有找到可解析的分享鏈"
        )

    return good_nodes, error_messages


def _try_decode_base64(raw_text: str) -> str:
    """
    嘗試把 raw_text 當作 base64 解碼。
    如果解碼成功且結果看起來像分享鏈，就回傳解碼結果。
    否則回傳原始文字。
    """
    stripped = raw_text.strip()

    # 如果已經有 URI 前綴，表示是純文字
    if _looks_like_uri(stripped):
        return stripped

    # 嘗試 base64 解碼
    try:
        # 補齊 padding
        missing_padding = len(stripped) % 4
        padded = stripped + "=" * (4 - missing_padding) if missing_padding else stripped

        decoded_bytes = base64.b64decode(padded, validate=False)
        decoded_text = decoded_bytes.decode("utf-8", errors="replace")

        # 檢查解碼後是否有 URI 前綴（驗證是否真的是 base64 的訂閱）
        if _looks_like_uri(decoded_text):
            return decoded_text
        else:
            # 解碼成功但內容不像分享鏈，可能是其他格式
            # 仍然回傳解碼結果，讓下游處理
            return decoded_text

    except Exception:
        # base64 解碼失敗，當作純文字
        return stripped


def _looks_like_uri(text: str) -> bool:
    """
    檢查一段文字是否「看起來像」含有分享鏈 URI。
    不需要嚴格驗證，只要包含任一個已知前綴就算。
    """
    text_lower = text.lower()
    for prefix in KNOWN_URI_PREFIXES:
        if prefix in text_lower:
            return True
    return False
