# 🤖 AGENTS.md — AI 開發者指南

> 本文件供 AI 編碼助手（Copilot、Claude、Gemini 等）理解此專案的架構與慣例。

---

## 📌 專案概覽

**ChainPort Gateway** 是一個 Windows 桌面 GUI 工具，用來管理多瀏覽器or多個applications 的代理出口(多進多出)。

**核心流程：**

```
訂閱 URL → 下載 → 解析成 Node → 組成 Chain → 映射到 Port → 產生核心配置 → 啟動進程
```

---

## 🏛️ 架構分層

```
┌──────────────────────────────────────────────────┐
│                    app/ (GUI)                     │   PySide6 介面
│  ui_main_window → 6 個 ui_pages_* 頁面           │   使用者操作
├──────────────────────────────────────────────────┤
│                  models/ (Data)                   │   資料結構 + JSON 持久化
│  Node, Chain, PortMapping, Subscription, AppState │   app_state.py 管理全部
├──────────────────────────────────────────────────┤
│                parsers/ (Parse)                   │   訂閱解析
│  subscription_fetcher → clash_yaml / v2rayn       │   uri_parsers 拆單行 URI
├──────────────────────────────────────────────────┤
│                  core/ (Engine)                   │   核心引擎適配器
│  CoreAdapterBase → SingBox / Xray / Mihomo        │   process_runner 管進程
└──────────────────────────────────────────────────┘
```

**依賴方向**（嚴格單向）：

```
app/ → models/ ← parsers/
app/ → core/ → models/
```

- `app/` 依賴 `models/`、`core/`、`parsers/`
- `core/` 依賴 `models/`
- `parsers/` 依賴 `models/`
- `models/` 不依賴任何其他本地套件

---

## 📐 資料模型（models/）

| 類別           | 檔案              | 說明                                              |
| :------------- | :---------------- | :------------------------------------------------ |
| `Node`         | `node.py`         | 一個代理節點（vmess/vless/trojan/ss/socks5/http） |
| `Subscription` | `subscription.py` | 一個訂閱來源（name + url + type）                 |
| `Chain`        | `chain.py`        | 一條鏈式代理（有序的 node_id 清單）               |
| `PortMapping`  | `port_mapping.py` | 一個端口映射（listen_port → chain_id）            |
| `AppState`     | `app_state.py`    | 全域狀態容器 + JSON 讀寫                          |

**所有 model 都實作：**

- `to_dict() → dict` — 序列化
- `from_dict(dict) → Self` — 反序列化
- `__repr__() → str` — debug 輸出

---

## ⚙️ 核心適配器（core/）

抽象介面 `CoreAdapterBase` 定義：

```python
class CoreAdapterBase(ABC):
    def generate_config(app_state) -> (config_text, config_path)
    def get_check_command(config_path, exe_path) -> list[str]
    def get_start_command(config_path, exe_path) -> list[str]
```

**三個實作：**

| Adapter          | 鏈式欄位            | 配置格式 |
| :--------------- | :------------------ | :------- |
| `SingBoxAdapter` | `detour`            | JSON     |
| `XrayAdapter`    | `proxySettings.tag` | JSON     |
| `MihomoAdapter`  | `dialer-proxy`      | YAML     |

**鏈式 outbound 命名規則：**

```
CHAIN_{chain_id}_H{hop_number}
```

例如 chain_id=`c1`，3 跳：`CHAIN_c1_H1`, `CHAIN_c1_H2`, `CHAIN_c1_H3`

---

## 🔍 解析器（parsers/）

**入口函式：**

```python
# 下載 + 自動偵測 + 解析
nodes, errors = fetch_and_parse(subscription)

# 只解析文字（測試用）
nodes, errors = parse_text_only(raw_text, sub_name, sub_type)
```

**自動偵測邏輯：**

- 如果文字包含 `proxies:` → Clash YAML
- 否則 → v2rayN（先嘗試 base64 解碼）

**URI 解析（uri_parsers.py）支援：**

`vmess://`, `vless://`, `trojan://`, `ss://`, `socks5://`, `socks://`, `http://`, `https://`

**錯誤回報格式：**

```
第 3 行解析失敗: 'vmess://xxxxx...' → 原因: Base64 解碼失敗
```

---

## 🖥️ GUI 頁面（app/）

| 頁面          | 檔案                        | 功能                               |
| :------------ | :-------------------------- | :--------------------------------- |
| Subscriptions | `ui_pages_subscriptions.py` | 新增/刪除/更新訂閱                 |
| Nodes         | `ui_pages_nodes.py`         | 顯示節點 + 搜尋篩選 + 手動新增     |
| Chains        | `ui_pages_chains.py`        | 建立/編輯 chain + Wrap Socks5      |
| Ports         | `ui_pages_ports.py`         | 端口映射 + 批量建立 + 複製代理設定 |
| Logs          | `ui_pages_logs.py`          | 核心 stdout/stderr 即時顯示        |
| Settings      | `ui_pages_settings.py`      | 核心類型/路徑設定                  |

**主窗口 `ui_main_window.py`：**

- 用 `QTabWidget` 組織 6 頁
- 底部永遠有 `Apply` / `Start` / `Stop` 三顆按鈕
- 跨執行緒 log 用 `LogBridge(QObject)` + `Signal` 安全傳送
- 任何頁面 `data_changed` 信號觸發時自動 `save_to_file()`

---

## 📏 編碼慣例

### 命名

- 變數名：`snake_case`，語義清楚（`airport_node_list`, `listen_port_number`）
- 常數：`UPPER_SNAKE_CASE`（`NODE_TYPE_VMESS`, `SUB_TYPE_CLASH`）
- 類別名：`PascalCase`（`AppState`, `SingBoxAdapter`）

### 註解

- 所有註解使用 **繁體中文**
- 每個函式都有 docstring 說明用途、參數、回傳值
- 重要邏輯步驟用 `# --- 第 N 步 ---` 標記

### 函式

- 每個函式 **≤ 40 行**
- 每個檔案只做一件事
- 所有函式都有 **type hints**

### 錯誤處理

- 解析錯誤不拋例外，收集到 `error_messages: list[str]` 回傳
- 錯誤訊息要包含：位置（行號/索引）+ 內容預覽 + 具體原因
- `fetch_and_parse()` 永不拋例外，所有錯誤都放進回傳值

---

## 🧪 測試

```bash
python -m pytest tests/ -v
```

| 測試檔                   | 數量 | 覆蓋範圍                                           |
| :----------------------- | :--- | :------------------------------------------------- |
| `test_clash_parser.py`   | 11   | YAML 解析、各協議欄位、邊界案例                    |
| `test_v2rayn_parser.py`  | 15   | 6 種 URI、base64 自動偵測、混合行                  |
| `test_chain_building.py` | 9    | Node 基本操作、chain 順序、detour tag、Wrap Socks5 |

---

## 🔧 新增協議/核心的步驟

### 新增一個 URI 協議

1. 在 `parsers/uri_parsers.py` 新增 `parse_xxx_uri()` 函式
2. 在 `parse_single_uri()` 加入對應的 `elif` 分支
3. 在 `models/node.py` 新增 `NODE_TYPE_XXX` 常數
4. 在三個 adapter 中新增 `_xxx_outbound()` 轉換函式
5. 在 `tests/test_v2rayn_parser.py` 新增測試案例

### 新增一個核心引擎

1. 在 `core/` 新增 `xxx_adapter.py`，繼承 `CoreAdapterBase`
2. 實作 `generate_config()`、`get_check_command()`、`get_start_command()`
3. 在 `app/ui_main_window.py` 的 `_get_current_adapter()` 加入分支
4. 在 `app/ui_pages_settings.py` 的下拉選單加入選項

---

## 📎 重要檔案路徑

| 用途          | 路徑                    |
| :------------ | :---------------------- |
| 狀態儲存      | `./state.json`          |
| sing-box 配置 | `./singbox_config.json` |
| Xray 配置     | `./xray_config.json`    |
| Mihomo 配置   | `./mihomo_config.yaml`  |
