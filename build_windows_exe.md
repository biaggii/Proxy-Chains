# 打包成 Windows EXE

## 方法一：PyInstaller（推薦）

### 1. 安裝 PyInstaller

```bash
pip install pyinstaller
```

### 2. 打包命令

```bash
pyinstaller --onefile --windowed --name ChainPortGateway --icon=icon.ico main.py
```

參數說明：
- `--onefile` : 打包成單一 exe 檔
- `--windowed` : 不顯示命令列黑窗
- `--name ChainPortGateway` : exe 檔名稱
- `--icon=icon.ico` : 圖示（可選，自己準備一個 .ico 檔）

### 3. 打包後的位置

```
dist/ChainPortGateway.exe
```

### 4. 使用方式

把以下檔案放在同一個資料夾：
- `ChainPortGateway.exe`
- `sing-box.exe`（或 `xray.exe` / `mihomo.exe`）

啟動 exe 後在 Settings 頁設定核心路徑即可。

## 方法二：Nuitka（更好的效能）

```bash
pip install nuitka
python -m nuitka --standalone --windows-disable-console --enable-plugin=pyside6 main.py
```

## 注意事項

1. 打包前確認 `pip install PySide6 requests pyyaml` 已安裝
2. state.json 會自動在 exe 旁邊產生
3. 核心執行檔（sing-box.exe 等）不會被打包進去，需要另外放
4. 如果 exe 太大，可以用 `--onedir` 代替 `--onefile`
