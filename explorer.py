from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QDir, QModelIndex, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFileSystemModel, QHBoxLayout, QInputDialog, QLabel,
    QMenu, QMessageBox, QPushButton, QTreeView, QVBoxLayout, QWidget,
)


class ExplorerWidget(QWidget):
    fileActivated = Signal(str)
    openFolderRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.root_path: Path | None = None
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.tree = QTreeView(self)
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.doubleClicked.connect(self._activate)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.rename_shortcut = QShortcut(QKeySequence("F2"), self.tree)
        self.rename_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.rename_shortcut.activated.connect(self.rename_selected)
        self.delete_shortcut = QShortcut(QKeySequence("Delete"), self.tree)
        self.delete_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.delete_shortcut.activated.connect(self.delete_selected)

        self.folder_label = QLabel("NO FOLDER OPEN", self)
        self.collapse_button = QPushButton("Collapse All", self)
        self.collapse_button.clicked.connect(self.tree.collapseAll)
        header = QHBoxLayout()
        header.addWidget(self.folder_label, 1)
        header.addWidget(self.collapse_button)

        self.empty_state = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.addStretch(1)
        empty_layout.addWidget(QLabel("You have not yet opened a folder.", self.empty_state))
        open_button = QPushButton("Open Folder", self.empty_state)
        open_button.clicked.connect(self.openFolderRequested)
        empty_layout.addWidget(open_button)
        empty_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.empty_state)
        layout.addWidget(self.tree)
        self.tree.hide()

    def set_root(self, path: str | None) -> None:
        if not path:
            self.root_path = None
            self.tree.hide()
            self.empty_state.show()
            self.folder_label.setText("NO FOLDER OPEN")
            return
        root = Path(path).resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"Project folder does not exist: {root}")
        self.root_path = root
        root_path = str(root)
        self.model.setRootPath(root_path)
        self.tree.setRootIndex(self.model.index(root_path))
        self.folder_label.setText(root.name or root_path)
        self.empty_state.hide()
        self.tree.show()

    def _activate(self, index: QModelIndex) -> None:
        path = self.model.filePath(index)
        if Path(path).is_file():
            self.fileActivated.emit(path)

    def _selected_path(self) -> Path | None:
        index = self.tree.currentIndex()
        path = self.model.filePath(index) if index.isValid() else ""
        return Path(path) if path else self.root_path

    def _creation_parent(self) -> Path | None:
        selected = self._selected_path()
        if selected is not None and selected.is_file():
            return selected.parent
        return selected

    def _show_context_menu(self, position) -> None:
        index = self.tree.indexAt(position)
        if index.isValid():
            self.tree.setCurrentIndex(index)
        menu = QMenu(self)
        menu.addAction("New File", self.new_file)
        menu.addAction("New Folder", self.new_folder)
        menu.addSeparator()
        menu.addAction("Rename", self.rename_selected, QKeySequence("F2"))
        menu.addAction("Delete", self.delete_selected, QKeySequence("Delete"))
        menu.addSeparator()
        menu.addAction("Reveal in File Explorer", self.reveal_selected)
        menu.addAction("Copy Path", self.copy_selected_path)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _prompt_name(self, title: str, prompt: str) -> str | None:
        name, accepted = QInputDialog.getText(self, title, prompt)
        if not accepted:
            return None
        name = name.strip()
        if not name or Path(name).name != name or "/" in name or "\\" in name:
            QMessageBox.warning(self, title, "Enter a single file or folder name.")
            return None
        return name

    def new_file(self) -> None:
        parent = self._creation_parent()
        if parent is None:
            self.openFolderRequested.emit()
            return
        name = self._prompt_name("New File", "File name:")
        if name is None:
            return
        try:
            path = parent / name
            path.touch(exist_ok=False)
            self.tree.setCurrentIndex(self.model.index(str(path)))
            self.fileActivated.emit(str(path))
        except OSError as exc:
            QMessageBox.warning(self, "New File Failed", str(exc))

    def new_folder(self) -> None:
        parent = self._creation_parent()
        if parent is None:
            self.openFolderRequested.emit()
            return
        name = self._prompt_name("New Folder", "Folder name:")
        if name is None:
            return
        try:
            path = parent / name
            path.mkdir()
            self.tree.setCurrentIndex(self.model.index(str(path)))
        except OSError as exc:
            QMessageBox.warning(self, "New Folder Failed", str(exc))

    def rename_selected(self) -> None:
        path = self._selected_path()
        if path is None or path == self.root_path:
            return
        name = self._prompt_name("Rename", "New name:")
        if name is None:
            return
        try:
            renamed = path.with_name(name)
            path.rename(renamed)
            self.tree.setCurrentIndex(self.model.index(str(renamed)))
        except OSError as exc:
            QMessageBox.warning(self, "Rename Failed", str(exc))

    def delete_selected(self) -> None:
        path = self._selected_path()
        if path is None or path == self.root_path:
            return
        answer = QMessageBox.question(
            self, "Delete", f"Delete '{path.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            else:
                shutil.rmtree(path)
        except OSError as exc:
            QMessageBox.warning(self, "Delete Failed", str(exc))

    def reveal_selected(self) -> None:
        path = self._selected_path()
        if path is not None:
            folder = path if path.is_dir() else path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def copy_selected_path(self) -> None:
        path = self._selected_path()
        if path is not None:
            QApplication.clipboard().setText(str(path))
