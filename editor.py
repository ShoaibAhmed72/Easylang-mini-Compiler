from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QToolTip, QTextEdit, QWidget

from highlighter import EasyLangHighlighter
from theme_manager import THEMES


class LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:
        self.editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    INDENT = "    "
    CORRECTIONS = {
        "prit": "print",
        "prnt": "print",
        "pirnt": "print",
        "whlie": "while",
        "els": "else",
        "strng": "string",
        "sring": "string",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        editor_font = QFont()
        editor_font.setFamilies(["Cascadia Code", "Consolas", "monospace"])
        editor_font.setPointSize(11)
        self.setFont(editor_font)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.line_number_area = LineNumberArea(self)
        self.highlighter = EasyLangHighlighter(self.document())
        self.error_location: tuple[int, int] | None = None
        self.correction_suggestion: tuple[int, int, str] | None = None
        self.textChanged.connect(self._suggest_correction)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._refresh_extra_selections)
        self._update_line_number_width()
        self._refresh_extra_selections()

    def line_number_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_width(self, _count: int = 0) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.line_number_area.setGeometry(QRect(rect.left(), rect.top(), self.line_number_width(), rect.height()))

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self.line_number_area)
        theme = THEMES[self.highlighter.theme_name]
        painter.fillRect(event.rect(), QColor(theme["editor"]))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        painter.setPen(QColor(theme["muted"]))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, top, self.line_number_area.width() - 6, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    def set_theme(self, theme_name: str) -> None:
        self.highlighter.set_theme(theme_name)
        self._refresh_extra_selections()
        self.line_number_area.update()

    def set_error_location(self, line: int | None, column: int = 1) -> None:
        self.error_location = (line, column) if line is not None else None
        self._refresh_extra_selections()

    def _refresh_extra_selections(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        current = QTextEdit.ExtraSelection()
        theme = THEMES[self.highlighter.theme_name]
        current.format.setBackground(QColor(theme["current_line"]))
        current.format.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        current.cursor = self.textCursor()
        current.cursor.clearSelection()
        selections.append(current)

        if self.error_location is not None:
            line, column = self.error_location
            block = self.document().findBlockByNumber(line - 1)
            if block.isValid():
                error = QTextEdit.ExtraSelection()
                error.cursor = QTextCursor(self.document())
                start = block.position() + min(max(column - 1, 0), len(block.text()))
                error.cursor.setPosition(start)
                if start < block.position() + len(block.text()):
                    error.cursor.movePosition(
                        QTextCursor.MoveOperation.NextWord,
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                else:
                    error.cursor.setPosition(block.position())
                    error.cursor.movePosition(
                        QTextCursor.MoveOperation.EndOfBlock,
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                error.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                error.format.setUnderlineColor(QColor(theme["icon_stop"]))
                selections.append(error)

        text = self.toPlainText()
        pos = self.textCursor().position()
        candidates = [pos, pos - 1]
        matching = {"(": ")", "[": "]", "{": "}", ")": "(", "]": "[", "}": "{"}
        for candidate in candidates:
            if not 0 <= candidate < len(text) or text[candidate] not in matching:
                continue
            char = text[candidate]
            opening = char in "([{"
            target = matching[char]
            depth = 0
            step = 1 if opening else -1
            scan = candidate
            while 0 <= scan < len(text):
                if text[scan] == char:
                    depth += 1
                elif text[scan] == target:
                    depth -= 1
                    if depth == 0:
                        for index in (candidate, scan):
                            selection = QTextEdit.ExtraSelection()
                            selection.format.setBackground(QColor(theme["bracket_match"]))
                            selection.format.setForeground(QColor(theme["text"]))
                            selection.cursor = QTextCursor(self.document())
                            selection.cursor.setPosition(index)
                            selection.cursor.movePosition(
                                QTextCursor.MoveOperation.NextCharacter,
                                QTextCursor.MoveMode.KeepAnchor,
                            )
                            selections.append(selection)
                        break
                scan += step
            break
        self.setExtraSelections(selections)

    def keyPressEvent(self, event) -> None:
        if (
            event.key() == Qt.Key.Key_Period
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self.correction_suggestion is not None
        ):
            start, end, correction = self.correction_suggestion
            cursor = self.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(correction)
            self.setTextCursor(cursor)
            QToolTip.hideText()
            return
        if event.key() == Qt.Key.Key_Tab and not event.modifiers():
            self.insertPlainText(self.INDENT)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            line = self.textCursor().block().text()
            indent = line[:len(line) - len(line.lstrip(" \t"))]
            super().keyPressEvent(event)
            self.insertPlainText(indent)
            return
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            super().keyPressEvent(event)
            return
        pairs = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
        text = event.text()
        cursor = self.textCursor()
        if text in ('"', "'") and not cursor.hasSelection():
            block_text = cursor.block().text()
            offset = cursor.positionInBlock()
            if offset < len(block_text) and block_text[offset] == text:
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                self.setTextCursor(cursor)
                return
        if text in pairs:
            closing = pairs[text]
            if cursor.hasSelection():
                start = cursor.selectionStart()
                selected = cursor.selectedText()
                cursor.insertText(text + selected + closing)
                cursor.setPosition(start + 1)
                cursor.setPosition(start + len(selected) + 1, QTextCursor.MoveMode.KeepAnchor)
            else:
                cursor.insertText(text + closing)
                cursor.movePosition(QTextCursor.MoveOperation.PreviousCharacter)
            self.setTextCursor(cursor)
            return
        if text in (")", "]", "}", '"', "'") and not cursor.hasSelection():
            block_text = cursor.block().text()
            offset = cursor.positionInBlock()
            if offset < len(block_text) and block_text[offset] == text:
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
                self.setTextCursor(cursor)
                return
        super().keyPressEvent(event)

    def _suggest_correction(self) -> None:
        cursor = self.textCursor()
        if cursor.hasSelection():
            return
        block = cursor.block()
        prefix = block.text()[:cursor.positionInBlock()]
        match = re.search(r"([A-Za-z_]\w*)[^\w]*$", prefix)
        correction = self.CORRECTIONS.get(match.group(1).lower()) if match else None
        if correction is not None:
            start = block.position() + match.start(1)
            end = start + len(match.group(1))
            suggestion = (start, end, correction)
            message = f"Did you mean '{correction}'? Press Ctrl+. to apply."
        else:
            line = block.text()
            stripped = line.strip()
            at_end = not line[cursor.positionInBlock():].strip()
            needs_semicolon = (
                at_end
                and stripped
                and not stripped.startswith("//")
                and not stripped.endswith((";", "{", "}"))
                and stripped not in ("START", "END")
                and re.match(r"^(int|string)\s+\w+|^\w+\s*=|^print\s*\(", stripped)
            )
            if needs_semicolon:
                position = block.position() + len(line.rstrip())
                suggestion = (position, position, ";")
                message = "Add a missing semicolon? Press Ctrl+. to apply."
            else:
                if self.correction_suggestion is not None:
                    QToolTip.hideText()
                self.correction_suggestion = None
                return
        if suggestion == self.correction_suggestion:
            return
        self.correction_suggestion = suggestion
        QToolTip.showText(
            self.mapToGlobal(self.cursorRect().bottomRight()),
            message,
            self,
            self.cursorRect(),
            3000,
        )

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            font = self.font()
            font.setPointSize(max(7, min(32, font.pointSize() + (1 if event.angleDelta().y() > 0 else -1))))
            self.setFont(font)
            self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
            self._update_line_number_width()
            event.accept()
            return
        super().wheelEvent(event)
