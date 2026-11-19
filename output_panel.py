from __future__ import annotations

import re
import math
from collections import deque

from PySide6.QtCore import Qt, QRectF, QSize, Signal, QPointF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QPlainTextEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from theme_manager import THEMES

OUTPUT_NAMES = (
    "Compilation Pipeline", "AST", "Control Flow Graph", "Tokens",
    "Symbol Table", "Three Address Code", "Debugger", "Output", "Errors",
)


class PipelineView(QWidget):
    """Interactive stage diagram populated only with real worker stage results."""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.theme_name = "Dark+"
        self.stages: list[dict] = []
        self.scene = QGraphicsScene(self)
        self.graph = ASTGraphicsView(self.scene, self)
        self.details = QLabel("Compile a program to inspect its pipeline stages.", self)
        self.details.setWordWrap(True)
        self.scene.selectionChanged.connect(self._selection_changed)
        controls = QHBoxLayout()
        zoom_in, zoom_out, fit = QPushButton("Zoom +", self), QPushButton("Zoom −", self), QPushButton("Fit to View", self)
        zoom_in.clicked.connect(lambda: self.graph.scale(1.2, 1.2))
        zoom_out.clicked.connect(lambda: self.graph.scale(1 / 1.2, 1 / 1.2))
        fit.clicked.connect(self.graph.fit_scene)
        controls.addWidget(zoom_in); controls.addWidget(zoom_out); controls.addWidget(fit); controls.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.graph, 1)
        layout.addWidget(self.details)

    def set_stages(self, stages: list[dict]) -> None:
        self.stages = list(stages or [])
        self.scene.clear()
        colors = THEMES[self.theme_name]
        if not self.stages:
            self.details.setText("No compilation session is available yet.")
            return
        width, height, gap = 250.0, 64.0, 36.0
        for index in range(len(self.stages) - 1):
            y1 = index * (height + gap) + height
            y2 = (index + 1) * (height + gap)
            self.scene.addLine(width / 2, y1, width / 2, y2, QPen(QColor(colors["muted"]), 2))
        for index, stage in enumerate(self.stages):
            y = index * (height + gap)
            status = str(stage.get("status", "pending")).lower()
            color = {
                "success": colors["icon_run"], "completed": colors["icon_run"],
                "failed": colors["icon_stop"], "running": colors["icon_compile"],
                "skipped": colors["muted"], "pending": colors["border"],
                "not_applicable": colors["border"],
            }.get(status, colors["border"])
            rect = QGraphicsRectItem(0, y, width, height)
            rect.setBrush(QBrush(QColor(colors["sidebar"])))
            rect.setPen(QPen(QColor(color), 3 if status in ("running", "failed") else 2))
            rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            rect.setData(0, index)
            self.scene.addItem(rect)
            title = self.scene.addText(str(stage.get("label", stage.get("name", "Stage"))))
            title.setDefaultTextColor(QColor(colors["text"]))
            title.setPos(10, y + 5)
            title.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            subtitle = self.scene.addText(status.replace("_", " ").title())
            subtitle.setDefaultTextColor(QColor(color))
            subtitle.setPos(10, y + 32)
            subtitle.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.graph.fit_scene()
        self.details.setText("Select a stage to inspect its actual result and diagnostic details.")

    def _selection_changed(self) -> None:
        selected = self.scene.selectedItems()
        if not selected:
            return
        index = selected[0].data(0)
        if index is None or not (0 <= int(index) < len(self.stages)):
            return
        stage = self.stages[int(index)]
        self.details.setText(
            f"{stage.get('label', stage.get('name', 'Stage'))} — "
            f"{str(stage.get('status', 'pending')).replace('_', ' ').title()}\\n"
            f"{stage.get('detail', 'No additional details were reported.')}"
        )

    def clear_content(self) -> None:
        self.stages = []
        self.scene.clear()
        self.details.setText("Compile a program to inspect its pipeline stages.")

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name if theme_name in THEMES else "Dark+"
        if self.stages:
            self.set_stages(self.stages)


class CFGView(QWidget):
    """CFG renderer for ControlFlowGraph objects produced from the parser AST."""
    lineRequested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.theme_name = "Dark+"
        self.graph_data = None
        self.scene = QGraphicsScene(self)
        self.graph = ASTGraphicsView(self.scene, self)
        self.details = QLabel("Compile a supported EasyLang program to build its CFG.", self)
        self.details.setWordWrap(True)
        self.scene.selectionChanged.connect(self._selection_changed)
        controls = QHBoxLayout()
        zoom_in, zoom_out, fit = QPushButton("Zoom +", self), QPushButton("Zoom −", self), QPushButton("Fit to View", self)
        zoom_in.clicked.connect(lambda: self.graph.scale(1.2, 1.2))
        zoom_out.clicked.connect(lambda: self.graph.scale(1 / 1.2, 1 / 1.2))
        fit.clicked.connect(self.graph.fit_scene)
        controls.addWidget(zoom_in); controls.addWidget(zoom_out); controls.addWidget(fit); controls.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.graph, 1)
        layout.addWidget(self.details)

    def set_graph(self, graph, error: str | None = None) -> None:
        self.graph_data = graph
        self.scene.clear()
        if graph is None or not graph.nodes:
            self.details.setText(error or "No CFG is available for this compilation.")
            return
        colors = THEMES[self.theme_name]
        adjacency = {ident: [] for ident in graph.nodes}
        for edge in graph.edges:
            adjacency.setdefault(edge.source, []).append(edge.target)
        levels = {graph.entry: 0}
        queue = deque([graph.entry])
        while queue:
            current = queue.popleft()
            for target in adjacency.get(current, []):
                if target not in levels:
                    levels[target] = levels[current] + 1
                    queue.append(target)
        max_level = max(levels.values(), default=0)
        buckets: dict[int, list[int]] = {}
        for ident in graph.nodes:
            buckets.setdefault(levels.get(ident, max_level + 1), []).append(ident)
        positions = {}
        for level, ids in buckets.items():
            ids.sort()
            for offset, ident in enumerate(ids):
                x = (offset - (len(ids) - 1) / 2) * 250.0
                positions[ident] = (x, level * 155.0)

        # Draw directed edges first so nodes remain visually on top.
        for edge in graph.edges:
            sx, sy = positions[edge.source]
            tx, ty = positions[edge.target]
            start = QPointF(sx, sy + 38)
            end = QPointF(tx, ty - 38)
            line = self.scene.addLine(start.x(), start.y(), end.x(), end.y(),
                                      QPen(QColor(colors["muted"]), 1.8))
            line.setZValue(-2)
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            size = 10.0
            p1 = end
            p2 = QPointF(end.x() - size * math.cos(angle - math.pi / 6),
                         end.y() - size * math.sin(angle - math.pi / 6))
            p3 = QPointF(end.x() - size * math.cos(angle + math.pi / 6),
                         end.y() - size * math.sin(angle + math.pi / 6))
            arrow = QGraphicsPolygonItem(QPolygonF([p1, p2, p3]))
            arrow.setBrush(QBrush(QColor(colors["muted"])))
            arrow.setPen(QPen(QColor(colors["muted"])))
            arrow.setZValue(-1)
            self.scene.addItem(arrow)
            if edge.label:
                label = self.scene.addText(edge.label)
                label.setDefaultTextColor(QColor(colors["text"]))
                label.setPos((sx + tx) / 2 + 5, (sy + ty) / 2)
                label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        for ident, item in graph.nodes.items():
            x, y = positions[ident]
            if item.kind == "decision":
                shape = QGraphicsEllipseItem(x - 92, y - 38, 184, 76)
            else:
                shape = QGraphicsRectItem(x - 105, y - 38, 210, 76)
            shape.setBrush(QBrush(QColor(colors["sidebar"])))
            shape.setPen(QPen(QColor(colors["accent"] if item.kind == "decision" else colors["border"]), 2))
            shape.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            shape.setData(0, ident)
            shape.setData(1, item.line)
            self.scene.addItem(shape)
            text = self.scene.addText(item.label)
            text.setDefaultTextColor(QColor(colors["text"]))
            text.setTextWidth(190)
            text.setPos(x - 95, y - 28)
            text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        self.graph.fit_scene()
        description = error or "CFG built from parser AST."
        self.details.setText(
            f"{description} Graph contains {len(graph.nodes)} nodes and {len(graph.edges)} directed edges. "
            "Select a statement block to navigate to its source line."
        )

    def _selection_changed(self) -> None:
        selected = self.scene.selectedItems()
        if not selected or self.graph_data is None:
            return
        ident = selected[0].data(0)
        if ident is None:
            return
        item = self.graph_data.nodes.get(int(ident))
        if item is None:
            return
        self.details.setText(f"{item.kind.title()} — {item.label}" +
                             (f" (line {item.line})" if item.line else ""))
        if item.line:
            self.lineRequested.emit(int(item.line), int(item.column or 1))

    def highlight_line(self, line: int) -> None:
        self.scene.clearSelection()
        for item in self.scene.items():
            if item.data(1) == line:
                item.setSelected(True)
                self.graph.centerOn(item)
                return

    def clear_content(self) -> None:
        self.graph_data = None
        self.scene.clear()
        self.details.setText("Compile a supported EasyLang program to build its CFG.")

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name if theme_name in THEMES else "Dark+"
        if self.graph_data is not None:
            self.set_graph(self.graph_data)



class ASTGraphicsView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def fit_scene(self) -> None:
        rect = self.scene().itemsBoundingRect().adjusted(-35, -35, 35, 35)
        if rect.isNull() or rect.isEmpty():
            return
        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        scale = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(scale, scale)
        event.accept()


class ASTView(QWidget):
    lineRequested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.theme_name = "Dark+"
        self.program = None
        self.tree_data = None
        self.tabs = QTabWidget(self)
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Node", "Value", "Line", "Column"])
        self.tree.itemSelectionChanged.connect(self._tree_selection)
        tree_page = QWidget(self)
        tree_layout = QVBoxLayout(tree_page)
        tree_buttons = QHBoxLayout()
        expand = QPushButton("Expand All", tree_page)
        collapse = QPushButton("Collapse All", tree_page)
        expand.clicked.connect(self.tree.expandAll)
        collapse.clicked.connect(self.tree.collapseAll)
        tree_buttons.addWidget(expand)
        tree_buttons.addWidget(collapse)
        tree_buttons.addStretch(1)
        tree_layout.addLayout(tree_buttons)
        tree_layout.addWidget(self.tree)
        self.scene = QGraphicsScene(self)
        self.graph = ASTGraphicsView(self.scene, self)
        self.scene.selectionChanged.connect(self._graph_selection)
        graph_page = QWidget(self)
        graph_layout = QVBoxLayout(graph_page)
        graph_buttons = QHBoxLayout()
        export = QPushButton("Export as PNG", graph_page)
        export.clicked.connect(self.export_png)
        graph_buttons.addStretch(1)
        graph_buttons.addWidget(export)
        graph_layout.addLayout(graph_buttons)
        graph_layout.addWidget(self.graph)
        self.tabs.addTab(tree_page, "Tree")
        self.tabs.addTab(graph_page, "Graph")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    def set_program(self, program) -> None:
        self.program = program
        self.set_tree_data(self._node(program))

    def set_cpp_tree(self, tree_data: dict) -> None:
        self.program = None
        self.set_tree_data(tree_data)

    def set_tree_data(self, root: dict) -> None:
        self.tree_data = root
        self.tree.clear()
        self._add_tree_node(root, self.tree.invisibleRootItem())
        self.tree.expandToDepth(1)
        self.scene.clear()
        next_leaf = [0]
        self._draw_node(root, 0, next_leaf)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-30, -30, 30, 30))
        self.graph.fit_scene()

    def highlight_line(self, line: int) -> None:
        self.scene.clearSelection()
        for item in self.scene.items():
            if item.data(0) == line:
                item.setSelected(True)
                self.graph.centerOn(item)
                return

    def clear_content(self) -> None:
        self.program = None
        self.tree.clear()
        self.scene.clear()

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name if theme_name in THEMES else "Dark+"
        if self.program is not None:
            self.set_program(self.program)
        elif self.tree_data is not None:
            self.set_tree_data(self.tree_data)

    def _node(self, node) -> dict:
        if node.kind == "program":
            result = {"name": "Program", "value": "", "line": node.line,
                      "column": getattr(node, "column", 1), "children": []}
            result["children"] = [self._node(child) for child in node.yes]
            return result
        if node.kind == "decl":
            result = {"name": "Declaration", "value": f"{node.typ} {node.name}", "line": node.line,
                      "column": getattr(node, "column", 1), "children": []}
            if node.expr:
                result["children"].append(self._node(node.expr))
            return result
        if node.kind == "assign":
            return {"name": "Assignment", "value": node.name, "line": node.line,
                    "column": getattr(node, "column", 1), "children": [self._node(node.expr)]}
        if node.kind == "print":
            return {"name": "Print", "value": "", "line": node.line,
                    "column": getattr(node, "column", 1), "children": [self._node(node.expr)]}
        if node.kind in ("if", "while"):
            result = {"name": node.kind.title(), "value": "", "line": node.line,
                      "column": getattr(node, "column", 1), "children": [self._node(node.expr)]}
            result["children"].append({
                "name": "Body" if node.kind == "while" else "Then",
                "value": "", "line": node.line, "column": getattr(node, "column", 1),
                "children": [self._node(child) for child in node.yes],
            })
            if node.no:
                result["children"].append({
                    "name": "Else", "value": "", "line": node.line,
                    "column": getattr(node, "column", 1),
                    "children": [self._node(child) for child in node.no],
                })
            return result
        values = {"literal": str(node.value), "variable": str(node.value),
                  "unary": "-", "binary": node.op}
        children = []
        if node.kind == "unary":
            children.append(self._node(node.right))
        elif node.kind == "binary":
            children.extend((self._node(node.left), self._node(node.right)))
        return {
            "name": {"literal": "Literal", "variable": "Variable", "unary": "Unary", "binary": "Binary"}[node.kind],
            "value": values[node.kind], "line": node.line,
            "column": getattr(node, "column", 1), "children": children,
        }

    def _add_tree_node(self, node: dict, parent) -> None:
        item = QTreeWidgetItem(parent, [node["name"], node["value"], str(node["line"]), str(node.get("column", 1))])
        item.setData(0, Qt.ItemDataRole.UserRole, (node["line"], node.get("column", 1)))
        for child in node["children"]:
            self._add_tree_node(child, item)

    def _draw_node(self, node: dict, depth: int, next_leaf: list[int]) -> tuple[float, float]:
        child_positions = [self._draw_node(child, depth + 1, next_leaf) for child in node["children"]]
        x = sum(point[0] for point in child_positions) / len(child_positions) if child_positions else next_leaf[0] * 180.0
        if not child_positions:
            next_leaf[0] += 1
        y = depth * 100.0
        label = node["name"] + (f"\n{node['value']}" if node["value"] else "")
        width = max(100.0, min(220.0, 16.0 + len(label.splitlines()[0]) * 8.0))
        rect = QGraphicsRectItem(x - width / 2, y, width, 54)
        theme = THEMES[self.theme_name]
        rect.setBrush(QBrush(QColor(theme["sidebar"])))
        rect.setPen(QPen(QColor(theme["accent"]), 1.5))
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        rect.setData(0, node["line"])
        rect.setData(1, node.get("column", 1))
        self.scene.addItem(rect)
        text = self.scene.addText(label)
        text.setDefaultTextColor(QColor(theme["text"]))
        text.setPos(x - width / 2 + 6, y + 4)
        text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        for child_x, child_y in child_positions:
            self.scene.addLine(x, y + 54, child_x, child_y, QPen(QColor(theme["muted"]), 1))
        return x, y

    def _tree_selection(self) -> None:
        items = self.tree.selectedItems()
        if items:
            location = items[0].data(0, Qt.ItemDataRole.UserRole)
            if location:
                self.lineRequested.emit(int(location[0]), int(location[1]))

    def _graph_selection(self) -> None:
        for item in self.scene.selectedItems():
            line = item.data(0)
            if line:
                column = item.data(1) or 1
                self.lineRequested.emit(int(line), int(column))
                return

    def export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export AST Graph", "ast.png", "PNG image (*.png)")
        if not path:
            return
        rect = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        pixmap = QPixmap(rect.size().toSize() + QSize(40, 40))
        pixmap.fill(QColor(THEMES[self.theme_name]["editor"]))
        painter = QPainter(pixmap)
        self.scene.render(painter, QRectF(20, 20, rect.width(), rect.height()), rect)
        painter.end()
        if not pixmap.save(path, "PNG"):
            QMessageBox.critical(self, "Export Failed", f"Could not write AST image: {path}")


class TokenTable(QWidget):
    lineRequested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tokens = []
        self.theme_name = "Dark+"
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter tokens...")
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["Index", "Type", "Lexeme", "Line", "Column"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.filter.textChanged.connect(self._apply_filter)
        self.table.currentCellChanged.connect(self._selection_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter)
        layout.addWidget(self.table)

    def set_tokens(self, tokens) -> None:
        self.tokens = list(tokens)
        self.table.setRowCount(len(tokens))
        colors = THEMES[self.theme_name]
        for row, token in enumerate(tokens):
            values = (row, token.type, token.lexeme, token.line, token.column)
            color = (
                colors["keyword"] if token.type in {"START", "END", "INT", "STRING", "PRINT", "IF", "ELSE", "WHILE"}
                else colors["number"] if token.type == "NUMBER"
                else colors["string"] if token.type == "STRING_LITERAL"
                else colors["identifier"] if token.type == "IDENTIFIER"
                else colors["accent"] if token.type in {"PLUS", "MINUS", "STAR", "SLASH", "EQ", "NE", "GT", "GE", "LT", "LE", "ASSIGN"}
                else colors["muted"]
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setForeground(QBrush(QColor(color)))
                self.table.setItem(row, column, item)
        self._apply_filter(self.filter.text())

    def _selection_changed(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        if 0 <= row < len(self.tokens):
            token = self.tokens[row]
            self.lineRequested.emit(int(token.line), int(token.column))

    def clear_content(self) -> None:
        self.tokens = []
        self.table.setRowCount(0)
        self.filter.clear()

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name if theme_name in THEMES else "Dark+"
        if self.tokens:
            self.set_tokens(self.tokens)

    def _apply_filter(self, query: str) -> None:
        needle = query.casefold()
        for row in range(self.table.rowCount()):
            visible = any(
                needle in self.table.item(row, column).text().casefold()
                for column in range(self.table.columnCount())
                if self.table.item(row, column) is not None
            )
            self.table.setRowHidden(row, not visible)


class SymbolTable(QWidget):
    lineRequested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Search symbols...")
        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Runtime Value", "Scope", "Initialized", "Declared at line"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(self._selection_changed)
        self.filter.textChanged.connect(self._apply_filter)
        self._symbol_rows: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.filter)
        layout.addWidget(self.table)

    def set_symbols(self, symbols: dict) -> None:
        self._symbol_rows = list(symbols.values())
        self.table.setRowCount(len(symbols))
        for row, (name, entry) in enumerate(symbols.items()):
            for column, value in enumerate((
                name, entry["type"],
                entry["value"] if entry["value"] is not None else (
                    "<not executed>" if entry.get("initialized", False) else "<uninitialized>"
                ),
                entry.get("scope", "global"),
                "Yes" if entry.get("initialized", False) else "No",
                entry.get("line", ""),
            )):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self._apply_filter(self.filter.text())

    def _apply_filter(self, query: str) -> None:
        needle = query.casefold()
        for row in range(self.table.rowCount()):
            visible = any(
                needle in self.table.item(row, column).text().casefold()
                for column in range(self.table.columnCount())
                if self.table.item(row, column) is not None
            )
            self.table.setRowHidden(row, not visible)

    def _selection_changed(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        if 0 <= row < len(self._symbol_rows):
            line = self._symbol_rows[row].get("line")
            if line:
                self.lineRequested.emit(int(line), 1)

    def clear_content(self) -> None:
        self._symbol_rows = []
        self.table.setRowCount(0)
        self.filter.clear()


class TACView(QWidget):
    lineRequested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tabs = QTabWidget(self)
        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["Instruction", "Operation", "Arg1", "Arg2", "Result", "Source Line"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.raw = QPlainTextEdit(self)
        self.raw.setReadOnly(True)
        self.source_map: list[int | None] = []
        self.table.currentCellChanged.connect(self._selection_changed)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Find in intermediate code...")
        self.search.textChanged.connect(self._apply_filter)
        self.copy_button = QPushButton("Copy TAC", self)
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.raw.toPlainText()))
        controls = QHBoxLayout()
        controls.addWidget(self.search, 1)
        controls.addWidget(self.copy_button)
        self.tabs.addTab(self.table, "Table")
        self.tabs.addTab(self.raw, "Raw Text")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.tabs)

    def set_tac(self, text: str, source_map: list[int | None] | None = None) -> None:
        self.raw.setPlainText(text)
        lines = text.splitlines()
        self.source_map = list(source_map or [])
        self.table.setRowCount(len(lines))
        for row, source in enumerate(lines, 1):
            operation, arg1, arg2, result = self._parse_line(source)
            source_line = self.source_map[row - 1] if row - 1 < len(self.source_map) else None
            values = (row, operation, arg1, arg2, result, source_line if source_line is not None else "")
            for column, value in enumerate(values):
                self.table.setItem(row - 1, column, QTableWidgetItem(str(value)))
        self._apply_filter(self.search.text())

    def _selection_changed(self, row: int, _column: int, _previous_row: int, _previous_column: int) -> None:
        if 0 <= row < len(self.source_map):
            line = self.source_map[row]
            if line:
                self.lineRequested.emit(int(line), 1)

    def _apply_filter(self, query: str) -> None:
        needle = query.casefold()
        for row in range(self.table.rowCount()):
            visible = any(
                needle in self.table.item(row, column).text().casefold()
                for column in range(self.table.columnCount())
                if self.table.item(row, column) is not None
            )
            self.table.setRowHidden(row, not visible)

    def _parse_line(self, text: str) -> tuple[str, str, str, str]:
        if text.endswith(":"):
            return "LABEL", "", "", text[:-1]
        match = re.fullmatch(r"IF_FALSE\s+(.+)\s+GOTO\s+(\S+)", text)
        if match:
            return "IF_FALSE GOTO", match.group(1), "", match.group(2)
        match = re.fullmatch(r"GOTO\s+(\S+)", text)
        if match:
            return "GOTO", "", "", match.group(1)
        if text.startswith("PRINT "):
            return "PRINT", text[6:], "", ""
        match = re.fullmatch(r"(\S+)\s*=\s*(.*?)\s*(==|!=|>=|<=|[+\-*/<>])\s*(.*?)", text)
        if match:
            return match.group(3), match.group(2), match.group(4), match.group(1)
        match = re.fullmatch(r"(\S+)\s*=\s*(.+)", text)
        if match:
            return "ASSIGN", match.group(2), "", match.group(1)
        return text, "", "", ""

    def clear_content(self) -> None:
        self.raw.clear()
        self.table.setRowCount(0)
        self.source_map = []
        self.search.clear()


class DebuggerView(QWidget):
    commandRequested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.variables = QTableWidget(0, 3, self)
        self.variables.setHorizontalHeaderLabels(["Name", "Type", "Value"])
        self.variables.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trace = QListWidget(self)
        self.summary = QLabel("Execution ready", self)
        self.start = QPushButton("Start", self)
        self.pause = QPushButton("Pause", self)
        self.step = QPushButton("Step Forward", self)
        self.continue_button = QPushButton("Resume", self)
        self.stop = QPushButton("Stop", self)
        self.start.clicked.connect(lambda: self.commandRequested.emit("start"))
        self.pause.clicked.connect(lambda: self.commandRequested.emit("pause"))
        self.step.clicked.connect(lambda: self.commandRequested.emit("step"))
        self.continue_button.clicked.connect(lambda: self.commandRequested.emit("continue"))
        self.stop.clicked.connect(lambda: self.commandRequested.emit("stop"))
        buttons = QHBoxLayout()
        buttons.addWidget(self.start)
        buttons.addWidget(self.pause)
        buttons.addWidget(self.step)
        buttons.addWidget(self.continue_button)
        buttons.addWidget(self.stop)
        panes = QHBoxLayout()
        panes.addWidget(self.variables)
        panes.addWidget(self.trace)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary)
        layout.addLayout(buttons)
        layout.addLayout(panes)

    def set_values(self, values: dict, types: dict | None = None) -> None:
        self.variables.setRowCount(len(values))
        for row, (name, value) in enumerate(values.items()):
            for column, item in enumerate((name, (types or {}).get(name, ""), value)):
                self.variables.setItem(row, column, QTableWidgetItem(str(item)))

    def add_step(self, line: int, kind: str, values: dict) -> None:
        self.trace.addItem(f"Line {line}: {kind}  {values}")
        self.trace.scrollToBottom()
        self.summary.setText(f"At line {line}: {kind} (pre-execution state)")

    def set_summary(self, text: str) -> None:
        self.summary.setText(text)

    def clear_content(self) -> None:
        self.variables.setRowCount(0)
        self.trace.clear()
        self.summary.setText("Execution ready")


class OutputPanel(QWidget):
    lineRequested = Signal(int, int)
    sourceLineSelected = Signal(int, int)
    debugCommand = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tabs = QTabWidget(self)
        self.views: dict[str, QWidget] = {}
        self.errors = QListWidget(self)
        self.errors.itemClicked.connect(self._activate_error)
        for name in OUTPUT_NAMES:
            if name == "Errors":
                view = self.errors
            elif name == "Compilation Pipeline":
                view = PipelineView(self)
            elif name == "Control Flow Graph":
                view = CFGView(self)
                view.lineRequested.connect(self.sourceLineSelected)
            elif name == "AST":
                view = ASTView(self)
                view.lineRequested.connect(self.sourceLineSelected)
            elif name == "Tokens":
                view = TokenTable(self)
                view.lineRequested.connect(self.sourceLineSelected)
            elif name == "Symbol Table":
                view = SymbolTable(self)
                view.lineRequested.connect(self.sourceLineSelected)
            elif name == "Three Address Code":
                view = TACView(self)
                view.lineRequested.connect(self.sourceLineSelected)
            elif name == "Debugger":
                view = DebuggerView(self)
                view.commandRequested.connect(self.debugCommand)
            else:
                view = QPlainTextEdit(self)
                view.setReadOnly(True)
                output_font = QFont()
                output_font.setFamilies(["Cascadia Code", "Consolas", "monospace"])
                output_font.setPointSize(10)
                view.setFont(output_font)
            self.views[name] = view
            self.tabs.addTab(view, name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

    def set_output(self, name: str, text: str) -> None:
        if name == "Errors":
            self.errors.clear()
            for line in str(text).splitlines() or [""]:
                self.errors.addItem(line)
                match = re.search(r"\bLine\s+(\d+)(?:\s*,\s*Column\s+(\d+))?\b", line, re.IGNORECASE)
                if match:
                    self.errors.item(self.errors.count() - 1).setData(
                        Qt.ItemDataRole.UserRole,
                        (int(match.group(1)), int(match.group(2) or 1)),
                    )
        elif isinstance(self.views[name], QPlainTextEdit):
            view = self.views[name]
            view.setPlainText(str(text))
        elif name == "Three Address Code":
            self.views[name].set_tac(str(text))

    def clear(self) -> None:
        for name, view in self.views.items():
            if name == "Errors":
                self.errors.clear()
            elif hasattr(view, "clear_content"):
                view.clear_content()
            else:
                view.clear()

    def set_pipeline(self, stages: list[dict]) -> None:
        self.views["Compilation Pipeline"].set_stages(stages)

    def set_cfg(self, graph, error: str | None = None) -> None:
        self.views["Control Flow Graph"].set_graph(graph, error)

    def set_tac(self, text: str, source_map: list[int | None] | None = None) -> None:
        self.views["Three Address Code"].set_tac(text, source_map)

    def highlight_source_line(self, line: int) -> None:
        self.views["AST"].highlight_line(line)
        self.views["Control Flow Graph"].highlight_line(line)

    def set_tokens(self, tokens) -> None:
        self.views["Tokens"].set_tokens(tokens)

    def set_ast(self, program) -> None:
        self.views["AST"].set_program(program)

    def set_cpp_ast(self, tree_data: dict) -> None:
        self.views["AST"].set_cpp_tree(tree_data)

    def set_symbols(self, symbols: dict) -> None:
        self.views["Symbol Table"].set_symbols(symbols)

    def set_debug_state(self, line: int, kind: str, values: dict, types: dict | None = None) -> None:
        view = self.views["Debugger"]
        view.set_values(values, types)
        view.add_step(line, kind, values)

    def set_theme(self, theme_name: str) -> None:
        self.views["Tokens"].set_theme(theme_name)
        self.views["AST"].set_theme(theme_name)
        self.views["Compilation Pipeline"].set_theme(theme_name)
        self.views["Control Flow Graph"].set_theme(theme_name)

    def select(self, name: str) -> None:
        self.tabs.setCurrentWidget(self.views[name])

    def _activate_error(self, item) -> None:
        location = item.data(Qt.ItemDataRole.UserRole)
        if location is not None:
            self.lineRequested.emit(*location)
