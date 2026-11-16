import json
import os
from pathlib import Path

import pytest

from models.app_state import AppState
from utils.autorun import set_autorun


@pytest.mark.skipif(os.name == "nt", reason="Linux bundled binary layout")
def test_default_core_paths_resolve_linux_bundle() -> None:
    state = AppState()

    assert state.core_exe_paths["sing-box"].endswith("bin/sing_box/sing-box")
    assert state.core_exe_paths["xray"].endswith("bin/xray/xray")
    assert state.core_exe_paths["mihomo"].endswith("bin/mihomo/mihomo")
    for path in state.core_exe_paths.values():
        assert Path(path).is_file()
        assert os.access(path, os.X_OK)


@pytest.mark.skipif(os.name == "nt", reason="Windows paths are not foreign on Windows")
def test_load_migrates_windows_paths_and_config_directory(tmp_path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "core_type": "sing-box",
                "core_exe_paths": {
                    "sing-box": "D:/Tools/Proxy-Chains/bin/sing_box/sing-box.exe",
                    "xray": "G:/Tools/Proxy-Chains/bin/Xray/xray.exe",
                    "mihomo": "G:/Tools/Proxy-Chains/bin/mihomo/mihomo.exe",
                },
                "config_output_dir": "D:/Tools/Proxy-Chains/logs",
            }
        ),
        encoding="utf-8",
    )

    state = AppState(str(state_file))
    state.load_from_file()

    assert state.core_exe_paths["sing-box"].endswith("bin/sing_box/sing-box")
    assert state.core_exe_paths["xray"].endswith("bin/xray/xray")
    assert state.core_exe_paths["mihomo"].endswith("bin/mihomo/mihomo")
    assert state.config_output_dir.endswith("logs")
    assert not state.config_output_dir.startswith("D:")


def test_linux_autorun_creates_and_removes_xdg_entry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    desktop_file = tmp_path / "xdg" / "autostart" / "chainport-gateway.desktop"

    assert set_autorun(True) is True
    content = desktop_file.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Name=ChainPort Gateway" in content
    assert "main.py" in content
    assert desktop_file.stat().st_mode & 0o777 == 0o644

    assert set_autorun(False) is True
    assert not desktop_file.exists()
