<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/GUI-PySide6-41CD52?style=for-the-badge&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/OS-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" />
</p>

<h1 align="center">⛓️ ChainPort Gateway</h1>

<p align="center">
  <strong>多瀏覽器 × 多端口 × 鏈式代理 — 一站式管理工具</strong>
</p>

<p align="center">
  訂閱解析 → 節點拆解 → 鏈式組合 → 多端口多出口 → 單一核心進程
</p>

---

## 🎯 為什麼需要 ChainPort Gateway？

當你在同時管理 **數十個瀏覽器 Profile**，每個 Profile 都需要 **不同的出口 IP**，
而你的流量還需要經過 **多跳代理鏈**（機場中轉 → 落地 Socks5）……

手動配置？那簡直是噩夢。

**ChainPort Gateway** 把這一切自動化：

```
📡 機場訂閱          🔗 鏈式代理              🔌 多端口
┌─────────────┐    ┌───────────────────┐    ┌──────────────────┐
│ Clash YAML  │───▶│ HK → JP → Socks5 │───▶│ :20001 → Chain A │──▶ Profile #1
│ v2rayN 分享 │    │ US → Socks5       │    │ :20002 → Chain B │──▶ Profile #2
│ 手動 Socks5 │    │ 單跳直連          │    │ :20003 → Chain C │──▶ Profile #3
└─────────────┘    └───────────────────┘    └──────────────────┘
                                                     │
                                              ┌──────┴──────┐
                                              │  單一核心進程  │
                                              │ sing-box.exe │
                                              └─────────────┘
```

---

## ✨ 功能亮點

| 機能              | 說明                                                  |
| :---------------- | :---------------------------------------------------- |
| 📡**訂閱解析**     | Clash YAML + v2rayN（base64 / 純文字），自動偵測格式  |
| 🔗**鏈式代理**     | 任意多跳：`Hop1 → Hop2 → Hop3 → …`，GUI 拖拽排序      |
| 🎯**Wrap Socks5**  | 選一條 pre-chain + socks5 落地 = 一鍵產生新鏈         |
| 🔌**多端口多出口** | N 個本地端口，各自綁定不同 chain，獨立出口 IP         |
| ⚡**單一核心**     | 只跑一個進程（sing-box / xray / mihomo 三選一）       |
| 🚀**TUN 模式**     | 接管全局流量防洩漏，具備智慧攔截 DNS 與防迴圈機制     |
| 📦**批量建立**     | 一鍵開 N 個端口，支援「同 chain」或「各節點單跳」模式 |
| 📋**一鍵複製**     | 複製所有代理地址，直接貼進 Application                |
| 💾**JSON 持久化**  | 所有狀態存在 `state.json`，人類可讀可編輯             |
| 🛡️**一鍵提權**     | 智能偵測 UAC，一鍵以系統管理員身分重啟 (TUN必須)      |

---

## 🚀 快速開始

### 1️⃣ 安裝依賴

```bash
pip install -r requirements.txt
pip install pywin32
```

### 2️⃣ 啟動

```bash
python main.py
```

### 3️⃣ 五步設定

```
Step 1  ⚙️ Settings     →  設定核心類型 + exe 路徑
Step 2  📡 Subscriptions →  新增訂閱 URL → Update Now
Step 3  🖧 Nodes         →  檢查節點 + 手動新增 socks5 落地
Step 4  🔗 Chains        →  建立鏈式代理（或 Wrap Socks5）
Step 5  🔌 Ports         →  建立端口映射（單一或批量）
        ────────────────────────────────────────────
        📝 Apply  →  產生配置檔 + 驗證
        ▶️ Start  →  啟動核心
        ⏹️ Stop   →  停止核心
```

### 4️⃣ Browsers OR Clients 設定

每個 Profile 的代理設定為：

```
代理類型: Socks5
代理地址: 127.0.0.1
代理端口: 20001  (或 20002, 20003, ...)
```

---

## 🏗️ 核心支援

三個核心引擎全部支援多端口 + 多跳鏈，同一時間只跑一個進程：

| 核心         | 鏈式方式                 | 配置格式 | 驗證命令                        |
| :----------- | :----------------------- | :------- | :------------------------------ |
| **sing-box** | `detour` 欄位反向串接    | JSON     | `sing-box check -c config.json` |
| **Xray**     | `proxySettings.tag` 串接 | JSON     | `xray run -test -c config.json` |
| **Mihomo**   | `dialer-proxy` 串接      | YAML     | `mihomo -t -f config.yaml`      |

---

## 🔗 鏈式代理原理

以 sing-box 為例，假設 Chain 有 3 跳：`NodeA → NodeB → SocksC`

```
                    ┌─────────────────────────────────────────┐
                    │            sing-box outbounds            │
                    │                                          │
  流量進入          │  H3 (SocksC)                             │
  IN_20001 ────────▶│    detour ──▶ H2 (NodeB)                │
                    │                  detour ──▶ H1 (NodeA)  │
                    │                               │          │
                    └───────────────────────────────┼──────────┘
                                                    ▼
                                              NodeA 伺服器
                                                    ▼
                                              NodeB 伺服器
                                                    ▼
                                              SocksC 落地
                                                    ▼
                                              🌐 目標網站
```

**生成的配置片段：**

```json
{
  "outbounds": [
    { "tag": "CHAIN_c1_H1", "type": "vmess",  "server": "a.com", "server_port": 443 },
    { "tag": "CHAIN_c1_H2", "type": "trojan", "server": "b.com", "server_port": 443, "detour": "CHAIN_c1_H1" },
    { "tag": "CHAIN_c1_H3", "type": "socks",  "server": "c.com", "server_port": 1080, "detour": "CHAIN_c1_H2" }
  ],
  "route": {
    "rules": [{ "inbound": ["IN_20001"], "outbound": "CHAIN_c1_H3" }]
  }
}
```

---

## 📁 專案結構

```
chainport_gateway/
│
├── main.py                          # 🚪 程式入口
├── state.json                       # 💾 狀態儲存（自動產生）
├── requirements.txt                 # 📦 Python 依賴
├── README.md                        # 📖 本文件
├── AGENTS.md                        # 🤖 AI 開發者指南
├── build_windows_exe.md             # 📦 打包教學
│
├── models/                          # 📐 資料模型
│   ├── node.py                      #    Node — 代理節點
│   ├── subscription.py              #    Subscription — 訂閱
│   ├── chain.py                     #    Chain — 鏈式代理
│   ├── port_mapping.py              #    PortMapping — 端口映射
│   └── app_state.py                 #    AppState — 全域狀態 + JSON 持久化
│
├── parsers/                         # 🔍 訂閱解析
│   ├── uri_parsers.py               #    6 種 URI 解析器
│   ├── clash_yaml_parser.py         #    Clash YAML 解析
│   ├── v2rayn_parser.py             #    v2rayN base64/純文字
│   └── subscription_fetcher.py      #    下載 + 自動偵測 + 統一入口
│
├── core/                            # ⚙️ 核心引擎
│   ├── core_adapter_base.py         #    抽象基底（ABC）
│   ├── singbox_adapter.py           #    sing-box 配置生成
│   ├── xray_adapter.py              #    Xray 配置生成
│   ├── mihomo_adapter.py            #    Mihomo 配置生成
│   └── process_runner.py            #    進程管理 + log 讀取
│
├── app/                             # 🖥️ PySide6 GUI
│   ├── ui_main_window.py            #    主窗口（6 Tab + 底部控制列）
│   ├── ui_pages_subscriptions.py    #    📡 訂閱管理頁
│   ├── ui_pages_nodes.py            #    🖧 節點管理頁
│   ├── ui_pages_chains.py           #    🔗 鏈管理頁
│   ├── ui_pages_ports.py            #    🔌 端口映射頁
│   ├── ui_pages_logs.py             #    📋 Log 顯示頁
│   └── ui_pages_settings.py         #    ⚙️ 設定頁
│
└── tests/                           # 🧪 測試（35 個，全部通過）
    ├── test_clash_parser.py          #    Clash 解析測試
    ├── test_v2rayn_parser.py         #    v2rayN + URI 解析測試
    └── test_chain_building.py        #    Chain 建構 + detour 邏輯測試
```

---

## 🧪 測試

```bash
python -m pytest tests/ -v
```

```
tests/test_chain_building.py    ✅ 9 passed
tests/test_clash_parser.py      ✅ 11 passed
tests/test_v2rayn_parser.py     ✅ 15 passed
───────────────────────────────────────────
                                ✅ 35 passed in 0.11s
```

---

## 📦 打包成 EXE

詳見 [build_windows_exe.md](build_windows_exe.md)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ChainPortGateway main.py
```

---

## 🛠️ 技術棧

| 技術             | 用途                          |
| :--------------- | :---------------------------- |
| **Python 3.11+** | 主語言                        |
| **PySide6**      | 桌面 GUI                      |
| **requests**     | 訂閱下載                      |
| **PyYAML**       | Clash YAML 解析               |
| **JSON**         | 狀態儲存 + sing-box/Xray 配置 |
| **subprocess**   | 核心進程管理                  |
| **threading**    | 背景 log 讀取                 |
| **pytest**       | 單元測試                      |

---

## 📝 設計原則

- 🎓 **教小學生等級的程式碼** — 每個函式 ≤ 40 行，繁體中文註解
- 📄 **每個檔案只做一件事** — 職責分明，好找好改
- 🔤 **看得懂的變數名** — `airport_node_list`, `landing_socks5`, `listen_port_number`
- 🛡️ **友善錯誤訊息** — 解析失敗會講「哪個訂閱、第幾行、什麼原因」
- 💾 **人類可讀的狀態檔** — `state.json` 用 UTF-8 + indent=2，可以直接開文字編輯器看

---

## 📄 License

MIT License — 自由使用、修改、分發。
