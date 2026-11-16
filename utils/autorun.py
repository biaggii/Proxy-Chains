import os
import sys
from pathlib import Path


APP_NAME = "ChainPortGateway"


def _application_command() -> str:
    """Return an XDG Desktop Entry Exec value for this app."""
    if getattr(sys, "frozen", False):
        executable = sys.executable
        args = []
    else:
        executable = sys.executable
        script = str(Path(__file__).resolve().parent.parent / "main.py")
        args = [script]

    # Desktop Entry Exec quoting uses double quotes, not shell quoting.
    def quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%")
        return f'"{escaped}"'

    return " ".join([quote(executable), *(quote(arg) for arg in args)])


def _set_linux_autorun(enable: bool) -> bool:
    """Create/remove the per-user XDG autostart desktop entry."""
    autostart_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
    desktop_file = autostart_dir / "chainport-gateway.desktop"
    try:
        if enable:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Version=1.0\n"
                "Name=ChainPort Gateway\n"
                "Comment=Proxy multi-chain manager\n"
                f"Exec={_application_command()}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            desktop_file.write_text(content, encoding="utf-8")
            desktop_file.chmod(0o644)
        else:
            desktop_file.unlink(missing_ok=True)
        return True
    except OSError as err:
        print(f"Failed to update Linux autostart entry: {err}")
        return False

def set_autorun(enable: bool) -> bool:
    """
    Enable or disable per-user login startup on the current platform.
    """
    if os.name == "nt":
        import winreg

        if getattr(sys, "frozen", False):
            app_path = sys.executable
        else:
            python_exe = sys.executable
            if python_exe.lower().endswith("python.exe"):
                pythonw_exe = python_exe[:-10] + "pythonw.exe"
                if os.path.exists(pythonw_exe):
                    python_exe = pythonw_exe
            script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
            app_path = f'"{python_exe}" "{script}"'

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                if enable:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, app_path)
                else:
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError:
                        pass
            return True
        except OSError as err:
            print(f"Failed to update Windows startup registry: {err}")
            return False

    if sys.platform.startswith("linux"):
        return _set_linux_autorun(enable)

    # macOS startup items need a LaunchAgent plist; don't claim success.
    return False
