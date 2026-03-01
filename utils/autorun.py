import os
import sys

def set_autorun(enable: bool) -> bool:
    """
    設定 Windows 開機自動執行。
    使用 winreg 修改 HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
    """
    if os.name != 'nt':
        return False
        
    import winreg
    
    app_name = "ChainPortGateway"
    
    # Check if we are running as a PyInstaller frozen exe
    if getattr(sys, 'frozen', False):
        app_path = sys.executable
    else:
        # Not frozen, point to main.py ran with pythonw
        app_path = f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))}"'
        
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, app_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass # Value didn't exist, which is fine
                
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Failed to set autorun: {e}")
        return False
