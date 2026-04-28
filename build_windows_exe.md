# Build Windows EXE

## Method 1: PyInstaller (Recommended)

### 1. Install PyInstaller

```bash
pip install pyinstaller
```

### 2. Build Command

```bash
pyinstaller --onefile --windowed --name ChainPortGateway --icon=icon.ico main.py
```

Parameter Explanation:
- `--onefile` : Build into a single executable file
- `--windowed` : Hide the command-line console window
- `--name ChainPortGateway` : Name of the output executable
- `--icon=icon.ico` : Application icon (optional, provide your own .ico file)

### 3. Output Location

```
dist/ChainPortGateway.exe
```

### 4. Usage Instructions

Place the following files in the same folder:
- `ChainPortGateway.exe`
- `sing-box.exe` (or `xray.exe` / `mihomo.exe`)

After starting the application, set the core executable path in the Settings page.

## Method 2: Nuitka (Better Performance)

```bash
pip install nuitka
python -m nuitka --standalone --windows-disable-console --enable-plugin=pyside6 main.py
```

## Important Notes

1. Before building, ensure `PySide6 requests pyyaml` are installed via `pip install`.
2. `state.json` will be generated automatically next to the executable.
3. Core executables (e.g., sing-box.exe) are not bundled inside the EXE and must be placed alongside it.
4. If the EXE is too large, you can use `--onedir` instead of `--onefile`.
