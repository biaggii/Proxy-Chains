"""
Shared feedback banner helper.

Replaces the four identical ``_set_feedback()`` / ``_show_banner()``
implementations that were copy-pasted across subscriptions, ports,
settings, and the main window.
"""

from PySide6.QtWidgets import QLabel

from app.ui_kit.theme import FEEDBACK_COLORS


def set_feedback_banner(label: QLabel, message: str, level: str) -> None:
    """Apply a coloured feedback banner to *label*.

    Parameters
    ----------
    label:
        The ``QLabel`` to update.
    message:
        Human-readable feedback text.
    level:
        One of ``"success"``, ``"warning"``, ``"error"``, ``"info"``.
    """
    background, foreground = FEEDBACK_COLORS.get(level, FEEDBACK_COLORS["info"])
    label.setText(message)
    label.setStyleSheet(
        f"padding: 8px 10px; border-radius: 8px; "
        f"background: {background}; color: {foreground}; "
        f"border: 1px solid {foreground};"
    )
