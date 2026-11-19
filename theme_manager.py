from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication


THEMES: dict[str, dict[str, str]] = {
    "Dark+": {
        "window": "#101426", "menu": "#171b35", "sidebar": "#1b2040",
        "activity": "#0c1023", "editor": "#0d1427", "tab_active": "#171b35",
        "tab_inactive": "#1b2040", "selection": "#43308d", "status": "#241b50",
        "text": "#eef0ff", "muted": "#a8afd0", "border": "#34365f",
        "accent": "#a855f7", "hover": "#29284f", "button": "#222744",
        "keyword": "#e879f9", "type": "#67e8f9", "function": "#fbbf24",
        "string": "#a7f3d0", "number": "#fb923c", "comment": "#8491b5",
        "identifier": "#93c5fd", "status_text": "#ffffff", "scrollbar_handle": "#56508a",
        "current_line": "#18223d", "bracket_match": "#40336d", "modified": "#fbbf24",
        "icon_run": "#22c55e", "icon_debug": "#38bdf8", "icon_stop": "#fb7185",
        "icon_compile": "#fbbf24", "icon_correct": "#a855f7",
    },
    "Light+": {
        "window": "#f5f3ff", "menu": "#ffffff", "sidebar": "#eeebff",
        "activity": "#e4ddff", "editor": "#ffffff", "tab_active": "#ffffff",
        "tab_inactive": "#eeeaff", "selection": "#d9ccff", "status": "#6d28d9",
        "text": "#28213f", "muted": "#756b91", "border": "#d8cef5",
        "accent": "#7c3aed", "hover": "#e5ddff", "button": "#faf8ff",
        "keyword": "#8b43b6", "type": "#167d83", "function": "#8a641d",
        "string": "#287a45", "number": "#bd572b", "comment": "#71836e",
        "identifier": "#2457a6", "status_text": "#ffffff", "scrollbar_handle": "#bdc9d9",
        "current_line": "#f1f5fb", "bracket_match": "#dceaff", "modified": "#a56b12",
        "icon_run": "#21865c", "icon_debug": "#216eb5", "icon_stop": "#c43e4b",
        "icon_compile": "#8a641d", "icon_correct": "#7c3aed",
    },
}


class ThemeManager:
    def __init__(self) -> None:
        self.theme_dir = Path(__file__).with_name("themes")

    def apply(self, app: QApplication, name: str) -> str:
        if name not in THEMES:
            name = "Dark+"
        stylesheet = (self.theme_dir / f"vscode_{'dark' if name == 'Dark+' else 'light'}.qss").read_text(
            encoding="utf-8"
        )
        for key, value in THEMES[name].items():
            stylesheet = stylesheet.replace(f"@{key}@", value)
        app.setStyleSheet(stylesheet)
        return name
