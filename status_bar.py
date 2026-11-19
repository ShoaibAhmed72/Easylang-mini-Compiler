from __future__ import annotations

from PySide6.QtWidgets import QLabel, QStatusBar


class StudioStatusBar(QStatusBar):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.position = QLabel("Ln 1, Col 1")
        self.language = QLabel("EasyLang")
        self.encoding = QLabel("UTF-8")
        self.compile_status = QLabel("No errors")
        for label in (self.position, self.language, self.encoding, self.compile_status):
            label.setContentsMargins(8, 0, 8, 0)
            self.addPermanentWidget(label)

    def set_position(self, line: int, column: int) -> None:
        self.position.setText(f"Ln {line}, Col {column}")

    def set_compile_status(self, error_count: int) -> None:
        self.compile_status.setText("No errors" if error_count == 0 else f"{error_count} errors")

    def set_language(self, language: str) -> None:
        self.language.setText(language)
