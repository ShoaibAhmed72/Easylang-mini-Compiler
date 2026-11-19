from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from theme_manager import THEMES


class EasyLangHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self.theme_name = "Dark+"
        self.set_theme(self.theme_name)

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name if theme_name in THEMES else "Dark+"
        colors = THEMES[self.theme_name]
        self.formats: dict[str, QTextCharFormat] = {}
        self._add("comment", colors["comment"], italic=True)
        self._add("string", colors["string"])
        self._add("number", colors["number"])
        self._add("type", colors["type"])
        self._add("keyword", colors["keyword"], bold=True)
        self._add("function", colors["function"])
        self._add("identifier", colors["identifier"])
        self.token_pattern = re.compile(
            r'(?P<comment>//.*$)'
            r'|(?P<string>"(?:[^"\\]|\\.)*")'
            r'|(?P<number>\b\d+(?:\.\d+)?\b)'
            r'|(?P<type>\b(?:int|string|float|bool)\b)'
            r'|(?P<keyword>\b(?:START|END|if|else|while|for)\b)'
            r'|(?P<function>\bprint\b)'
            r'|(?P<identifier>\b[A-Za-z_]\w*\b)'
        )
        self.rehighlight()

    def _add(self, name: str, color: str, *, bold: bool = False, italic: bool = False) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        self.formats[name] = fmt

    def highlightBlock(self, text: str) -> None:
        for match in self.token_pattern.finditer(text):
            name = match.lastgroup
            if name is not None:
                self.setFormat(match.start(), match.end() - match.start(), self.formats[name])
