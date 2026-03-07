"""
subscription_fetcher.py — 訂閱下載與解析的統一入口

這個模組負責：
1. 用 requests 下載訂閱的原始文字
2. 根據訂閱類型（Clash / v2rayN / 自動偵測）呼叫對應的解析器
3. 回傳解析後的節點列表 + 錯誤訊息

使用方式：
    nodes, errors = fetch_and_parse(subscription)
"""

from datetime import datetime, timezone, timedelta

import requests

from models.node import Node
from models.subscription import (
    Subscription,
    SUB_TYPE_CLASH,
    SUB_TYPE_V2RAYN,
    SUB_TYPE_AUTO,
)
from parsers.clash_yaml_parser import parse_clash_yaml
from parsers.v2rayn_parser import parse_v2rayn_subscription


# ============================================================
# 下載訂閱文字
# ============================================================

def download_subscription_text(
    url: str,
    timeout_seconds: int = 30,
) -> str:
    """
    用 requests 下載訂閱 URL，回傳原始文字內容。
    失敗會拋出 ConnectionError 或 TimeoutError，附帶清楚的訊息。
    """
    try:
        response = requests.get(
            url,
            timeout=timeout_seconds,
            headers={
                # 模擬 Clash Verge 的 User-Agent，讓機場回傳正確格式
                "User-Agent": "ClashForWindows/0.20.30",
            },
        )
        response.raise_for_status()
        return response.text

    except requests.exceptions.Timeout:
        raise TimeoutError(
            f"Subscription download timed out ({timeout_seconds} seconds): {url}"
        )
    except requests.exceptions.ConnectionError as err:
        raise ConnectionError(
            f"Unable to connect to subscription server: {url}\nReason: {err}"
        )
    except requests.exceptions.HTTPError as err:
        raise ConnectionError(
            f"Subscription server returned an error (HTTP {response.status_code}): {url}\nReason: {err}"
        )
    except Exception as err:
        raise ConnectionError(
            f"Unexpected error while downloading subscription: {url}\nReason: {err}"
        )


# ============================================================
# 自動偵測訂閱類型
# ============================================================

def detect_subscription_type(raw_text: str) -> str:
    """
    根據內容自動判斷訂閱類型。
    - 如果內容看起來像 YAML（包含 "proxies:" 關鍵字），就當 Clash
    - 否則當 v2rayN
    """
    # 先檢查原始文字
    if _has_yaml_proxies_keyword(raw_text):
        return SUB_TYPE_CLASH

    # 也可能 base64 解碼後是 YAML（雖然不常見，但防一下）
    # 但通常 Clash 訂閱不會 base64 編碼，所以這裡不多做

    return SUB_TYPE_V2RAYN


def _has_yaml_proxies_keyword(text: str) -> bool:
    """檢查文字裡是否有 'proxies:' 這個 YAML key"""
    # 用簡單的字串搜尋，不用完整解析
    for line in text.splitlines()[:50]:  # 只看前 50 行就夠了
        stripped = line.strip()
        if stripped.startswith("proxies:") or stripped == "proxies:":
            return True
    return False


# ============================================================
# 統一入口：下載 + 解析
# ============================================================

def fetch_and_parse(
    subscription: Subscription,
) -> tuple[list[Node], list[str]]:
    """
    下載訂閱並解析成節點列表。

    參數：
    - subscription: Subscription 物件（包含 name, url, sub_type）

    回傳值：
    - (成功的節點清單, 錯誤訊息清單)

    這個函式不會拋出例外——所有錯誤都放進 error_messages 裡回傳。
    """
    sub_name = subscription.name
    sub_url = subscription.url
    sub_type = subscription.sub_type

    # --- 第 1 步：下載 ---
    try:
        raw_text = download_subscription_text(sub_url)
    except Exception as err:
        return [], [f"Subscription '{sub_name}' download failed: {err}"]

    # --- 第 2 步：判斷類型（如果是 auto） ---
    if sub_type == SUB_TYPE_AUTO:
        sub_type = detect_subscription_type(raw_text)

    # --- 第 3 步：解析 ---
    if sub_type == SUB_TYPE_CLASH:
        node_list, error_list = parse_clash_yaml(raw_text, sub_name)
    elif sub_type == SUB_TYPE_V2RAYN:
        node_list, error_list = parse_v2rayn_subscription(raw_text, sub_name)
    else:
        node_list = []
        error_list = [f"Subscription '{sub_name}' has unsupported type '{sub_type}'"]

    # --- 第 4 步：更新訂閱的 metadata ---
    # 取得台北時間 (UTC+8)
    taipei_tz = timezone(timedelta(hours=8))
    subscription.last_update = datetime.now(taipei_tz).isoformat()
    subscription.node_count = len(node_list)
    subscription.raw_text = raw_text

    return node_list, error_list


# ============================================================
# 僅解析（不下載），用於測試或手動貼上文字
# ============================================================

def parse_text_only(
    raw_text: str,
    sub_name: str = "Manual Input",
    sub_type: str = SUB_TYPE_AUTO,
) -> tuple[list[Node], list[str]]:
    """
    只解析文字，不下載。方便測試或手動貼上內容。
    """
    if sub_type == SUB_TYPE_AUTO:
        sub_type = detect_subscription_type(raw_text)

    if sub_type == SUB_TYPE_CLASH:
        return parse_clash_yaml(raw_text, sub_name)
    elif sub_type == SUB_TYPE_V2RAYN:
        return parse_v2rayn_subscription(raw_text, sub_name)
    else:
        return [], [f"Unsupported subscription type '{sub_type}'"]
