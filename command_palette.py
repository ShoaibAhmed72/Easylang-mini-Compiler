from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


class CommandPalette(QDialog):
    def __init__(self, actions: list[QAction], parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self.setWindowTitle("Command Palette")
        self.setMinimumWidth(560)
        self.actions = actions
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Type a command...")
        self.list = QListWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._run_current)
        self.list.itemActivated.connect(self._run_item)

    def open(self) -> None:
        self.search.clear()
        self._filter("")
        if self.list.count():
            self.list.setCurrentRow(0)
        self.adjustSize()
        self.show()
        self.search.setFocus()

    def _filter(self, text: str) -> None:
        query = text.casefold()
        self.list.clear()
        for action in self.actions:
            if not action.isEnabled() or query not in action.text().replace("&", "").casefold():
                continue
            item = QListWidgetItem(action.text().replace("&", ""))
            item.setData(Qt.ItemDataRole.UserRole, action)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self._run_item(item)

    def _run_item(self, item: QListWidgetItem) -> None:
        action = item.data(Qt.ItemDataRole.UserRole)
        self.hide()
        if action is not None:
            action.trigger()
