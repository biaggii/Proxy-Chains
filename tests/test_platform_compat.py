import os

from app.ui_main_window import MainWindow


def test_admin_check_is_safe_on_current_platform() -> None:
    # In particular, this must not access ctypes.windll on Linux/macOS.
    expected = hasattr(os, "geteuid") and os.geteuid() == 0
    assert MainWindow._is_admin(None) is expected
