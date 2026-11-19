from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QDockWidget,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit,
    QSplitter, QTabWidget, QToolBar, QVBoxLayout, QWidget, QInputDialog, QStyle, QToolButton,
)

import easylang_studio as core
from command_palette import CommandPalette
from editor import CodeEditor
from explorer import ExplorerWidget
from output_panel import OutputPanel
from status_bar import StudioStatusBar
from theme_manager import THEMES, ThemeManager
from visualizations.cfg_builder import build_cfg
from cpp_safe_fixes import CppSafeFixer
from cpp_visualizer import analyze_cpp


SOURCE_FILTER = (
    "EasyLang files (*.el *.easy *.txt);;"
    "C++ source (*.cpp *.cc *.cxx *.h *.hpp);;All files (*)"
)


class CompileWorker(QThread):
    completed = Signal(object)
    statement = Signal(int, object, str)
    stageChanged = Signal(object)
    visualizationReady = Signal(object, object)

    def __init__(self, source: str, path: str | None, language: str, run: bool, debug: bool, parent=None) -> None:
        super().__init__(parent)
        self.source = source
        self.path = path
        self.language = language
        self.run_program = run
        self.debug_program = debug
        self.stop_event = threading.Event()
        self._debug_condition = threading.Condition()
        self._debug_paused = debug
        self._pause_after_step = False
        self.symbol_types: dict[str, str] = {}

    def request_stop(self) -> None:
        self.stop_event.set()
        with self._debug_condition:
            self._debug_condition.notify_all()

    def step_once(self) -> None:
        with self._debug_condition:
            self._debug_paused = False
            self._pause_after_step = True
            self._debug_condition.notify_all()

    def pause_execution(self) -> None:
        with self._debug_condition:
            self._debug_paused = True
            self._pause_after_step = False

    def continue_execution(self) -> None:
        with self._debug_condition:
            self._debug_paused = False
            self._pause_after_step = False
            self._debug_condition.notify_all()

    def _before_statement(self, statement, values) -> None:
        self.statement.emit(statement.line, dict(values), statement.kind)
        with self._debug_condition:
            while self._debug_paused and not self.stop_event.is_set():
                self._debug_condition.wait(0.1)
            if self._pause_after_step:
                self._debug_paused = True
                self._pause_after_step = False

    def run(self) -> None:
        result: dict[str, object] = {
            "outputs": {}, "status": "", "error": None, "tokens": [],
            "program": None, "symbols": {}, "tac": "", "tac_source_map": [], "cfg": None,
            "pipeline": [
                {"id": "source", "label": "Source Code", "status": "success", "detail": "Source text captured from the active editor."},
                {"id": "lexer", "label": "Lexical Analysis", "status": "pending", "detail": "Lexer has not run."},
                {"id": "parser", "label": "Syntax Analysis", "status": "pending", "detail": "Parser has not run."},
                {"id": "ast", "label": "Abstract Syntax Tree", "status": "pending", "detail": "Parser has not produced an AST."},
                {"id": "semantic", "label": "Semantic Analysis", "status": "pending", "detail": "Semantic analysis has not run."},
                {"id": "symbols", "label": "Symbol Table", "status": "pending", "detail": "Semantic symbols are not available."},
                {"id": "tac", "label": "Intermediate Code", "status": "pending", "detail": "Code generation has not run."},
                {"id": "execution", "label": "Execution", "status": "pending", "detail": "Execution has not been requested."},
            ],
            "visualization_error": None,
        }
        outputs: dict[str, str] = result["outputs"]
        stages = result["pipeline"]
        stage_by_id = {stage["id"]: stage for stage in stages}
        current_stage = None

        def stage_running(stage_id: str, detail: str) -> None:
            nonlocal current_stage
            current_stage = stage_id
            stage_by_id[stage_id].update(status="running", detail=detail)
            self.stageChanged.emit([dict(stage) for stage in stages])

        def stage_success(stage_id: str, detail: str) -> None:
            stage_by_id[stage_id].update(status="success", detail=detail)
            self.stageChanged.emit([dict(stage) for stage in stages])

        try:
            is_cpp = self.language == "C++17" or (
                self.path and Path(self.path).suffix.lower() in {".cpp", ".cc", ".cxx"}
            )
            if is_cpp:
                cpp_labels = {"lexer": "C++ Preprocessing", "parser": "C++ Syntax / Parsing",
                              "ast": "C++ AST (compiler internal)", "semantic": "C++ Semantic Analysis",
                              "symbols": "C++ Symbol Resolution", "tac": "Native Code Generation / Linking",
                              "execution": "C++ Program Execution"}
                for stage in stages:
                    stage["label"] = cpp_labels.get(stage["id"], stage["label"])
                self.stageChanged.emit([dict(stage) for stage in stages])
                if not self.path:
                    raise RuntimeError("Save the C++ source file before compiling.")
                source_path = Path(self.path)
                compiler = core.os.environ.get("EASYLANG_GXX") or core.shutil.which("g++")
                if not compiler:
                    raise RuntimeError("GCC g++ not found. Install GCC or set EASYLANG_GXX.")
                build_dir = source_path.parent / "build" / "cpp"
                build_dir.mkdir(parents=True, exist_ok=True)
                executable = build_dir / (source_path.stem + (".exe" if core.os.name == "nt" else ""))
                # C++ phases are real compiler operations, not placeholder labels.
                for stage in stages:
                    stage.update(status="pending", detail="Waiting for C++ compiler phase.")
                stage_running("lexer", "C++ compiler front-end: preprocessing and token expansion (-E).")
                pre = core.subprocess.run([compiler, "-std=c++17", "-E", str(source_path)], capture_output=True, text=True, timeout=30)
                if pre.returncode:
                    stage_by_id["lexer"].update(status="error", detail="Preprocessing failed; see compiler diagnostics.")
                    outputs["Errors"] = pre.stderr
                    raise RuntimeError("C++ preprocessing failed.\n" + pre.stderr)
                stage_success("lexer", f"Preprocessing completed ({len(pre.stdout.splitlines())} expanded lines).")
                stage_running("parser", "C++ syntax analysis and parsing via g++ -fsyntax-only.")
                syntax = core.subprocess.run([compiler, "-std=c++17", "-fsyntax-only", str(source_path)], capture_output=True, text=True, timeout=30)
                if syntax.returncode:
                    stage_by_id["parser"].update(status="error", detail="C++ syntax/type diagnostics detected.")
                    outputs["Errors"] = syntax.stderr
                    raise RuntimeError("C++ syntax/semantic analysis failed.\n" + syntax.stderr)
                stage_success("parser", "Syntax and front-end semantic checks passed.")
                stage_success("ast", "AST is generated internally by the compiler front-end; external AST dump is not enabled.")
                stage_success("semantic", "C++ compiler front-end type and semantic checks passed.")
                stage_success("symbols", "Symbol resolution completed inside the C++ compiler; no standalone symbol table is exposed.")
                stage_running("tac", "Compiling and linking C++17 object code into an executable.")
                build = core.subprocess.run([compiler, "-std=c++17", str(source_path), "-o", str(executable)], capture_output=True, text=True, timeout=30)
                if build.returncode:
                    stage_by_id["tac"].update(status="error", detail="Code generation/linking failed; see diagnostics.")
                    outputs["Errors"] = build.stderr
                    raise RuntimeError("C++ code generation/linking failed.\n" + build.stderr)
                stage_success("tac", "Native code generation and linking completed successfully.")
                if self.run_program:
                    stage_running("execution", "Running the compiled C++17 executable (10-second limit).")
                    try:
                        execution = core.subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
                        outputs["Output"] = execution.stdout + execution.stderr
                        if execution.returncode:
                            stage_by_id["execution"].update(status="error", detail=f"Program exited with code {execution.returncode}.")
                            result["status"] = "C++ execution completed with non-zero exit code"
                        else:
                            stage_success("execution", "C++ program executed successfully.")
                            result["status"] = "C++ build/run finished"
                    except core.subprocess.TimeoutExpired:
                        stage_by_id["execution"].update(status="error", detail="Execution exceeded the 10-second limit.")
                        outputs["Output"] = "Execution stopped: 10-second time limit exceeded."
                        result["status"] = "C++ execution timed out"
                else:
                    stage_by_id["execution"].update(status="not_applicable", detail="Run was not requested; compilation only.")
                    outputs["Output"] = "C++ compilation succeeded. Run was not requested."
                    result["status"] = "C++ compilation succeeded"
            else:
                stage_running("lexer", "Tokenizing the active source with the existing EasyLang Lexer.")
                tokens = core.Lexer(self.source).scan()
                stage_success("lexer", f"Lexer completed and produced {len(tokens) - 1} source tokens.")
                result["tokens"] = tokens[:-1]
                outputs["Tokens"] = "Index\tType\tLexeme\tLine\tColumn\n" + "\n".join(
                    f"{index}\t{token.type}\t{token.lexeme}\t{token.line}\t{token.column}"
                    for index, token in enumerate(tokens[:-1])
                )
                stage_running("parser", "Parsing lexer tokens with the existing recursive-descent Parser.")
                program = core.Parser(tokens).parse()
                stage_success("parser", "Parser completed without syntax diagnostics.")
                result["program"] = program
                stage_success("ast", "AST is the actual Stmt/Expr tree returned by Parser.parse().")
                outputs["AST"] = core.ast_text(program)
                try:
                    result["cfg"] = build_cfg(program)
                except Exception as visualization_error:
                    result["visualization_error"] = f"CFG construction failed: {visualization_error}"
                self.visualizationReady.emit(program, result["cfg"])
                stage_running("semantic", "Checking declarations, initialization, types and expressions.")
                semantic = core.SemanticAnalyzer()
                semantic.analyze(program)
                stage_success("semantic", "Semantic analysis completed without semantic diagnostics.")
                self.symbol_types = {
                    name: entry["type"] for name, entry in semantic.symbols.items()
                }
                result["symbols"] = {
                    name: {
                        "type": entry["type"], "value": entry["value"],
                        "scope": "global", "line": semantic.declarations[name][0],
                        "initialized": name in semantic.initialized,
                    }
                    for name, entry in semantic.symbols.items()
                }
                stage_success("symbols", f"Semantic analyzer supplied {len(result['symbols'])} symbol(s); runtime values remain uninitialized until execution.")
                outputs["Symbol Table"] = "NAME\tTYPE\tVALUE\tSCOPE\tDECLARED AT LINE\n" + "\n".join(
                    f"{name}\t{item['type']}\t{item['value'] if item['value'] is not None else '<uninitialized>'}"
                    f"\tglobal\t{semantic.declarations[name][0]}"
                    for name, item in semantic.symbols.items()
                )
                stage_running("tac", "Generating intermediate code using the existing CodeGenerator.")
                generator = core.CodeGenerator()
                tac = generator.generate(program)
                result["tac_source_map"] = list(generator.source_map)
                stage_success("tac", f"Code generation completed ({len(tac.splitlines())} instruction/label line(s)); source lines are mapped where emitted by the generator.")
                result["tac"] = tac
                outputs["Three Address Code"] = tac
                if self.run_program:
                    stage_running("execution", "Interpreter execution is in progress.")
                    vm = core.Interpreter(
                        hook=self._before_statement if self.debug_program else None,
                        stop=self.stop_event,
                    )
                    output = vm.run(program)
                    stage_success("execution", f"Interpreter completed successfully after {vm.steps} execution step(s).")
                    outputs["Output"] = output
                    for name, value in vm.values.items():
                        semantic.symbols[name]["value"] = value
                        result["symbols"][name]["value"] = value
                    outputs["Symbol Table"] = "NAME\tTYPE\tVALUE\tSCOPE\tDECLARED AT LINE\n" + "\n".join(
                        f"{name}\t{item['type']}\t{item['value'] if item['value'] is not None else '<uninitialized>'}"
                        f"\tglobal\t{semantic.declarations[name][0]}"
                        for name, item in semantic.symbols.items()
                    )
                    result["steps"] = vm.steps
                    result["values"] = vm.values
                    if self.debug_program:
                        outputs["Debugger"] = (
                            "Execution trace is available at statement granularity in this build.\n"
                            f"Statements executed: {vm.steps}\nVariables: {vm.values}\n\nOutput:\n{output}"
                        )
                else:
                    stage_by_id["execution"].update(status="skipped", detail="Compile-only operation; the interpreter was not invoked.")
                result["status"] = (
                    "Debug run completed" if self.debug_program
                    else "Run completed successfully" if self.run_program
                    else "Compilation successful"
                )
        except Exception as error:
            result["error"] = error
            if current_stage and stage_by_id[current_stage].get("status") == "running":
                stage_by_id[current_stage].update(status="failed", detail=str(error))
        result["outputs"] = outputs
        self.completed.emit(result)


def _action_icon(kind: str) -> QIcon:
    pixmap = QPixmap(22, 22)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = THEMES["Dark+"].get(f"icon_{kind}", THEMES["Dark+"].get("icon_compile", THEMES["Dark+"]["accent"]))
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    if kind == "run":
        path = QPainterPath()
        path.moveTo(6, 3)
        path.lineTo(19, 11)
        path.lineTo(6, 19)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "stop":
        painter.drawRect(5, 5, 12, 12)
    elif kind == "debug":
        painter.drawEllipse(7, 6, 9, 10)
        painter.drawEllipse(5, 3, 5, 5)
        painter.drawEllipse(13, 3, 5, 5)
        painter.setPen(QColor(color))
        for y in (8, 13):
            painter.drawLine(3, y, 7, y)
            painter.drawLine(16, y, 20, y)
    else:
        painter.setPen(QColor(color))
        painter.drawEllipse(5, 5, 12, 12)
        painter.drawEllipse(9, 9, 4, 4)
        for x, y, dx, dy in ((10, 2, 0, 3), (10, 17, 0, 3), (2, 10, 3, 0), (17, 10, 3, 0)):
            painter.drawLine(x, y, x + dx, y + dy)
    painter.end()
    return QIcon(pixmap)


class GrammarDialog(QDialog):
    """Grammar workbench UI; grammar algorithms remain in the compiler module."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EasyLang - Grammar Workbench")
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.grammar = QPlainTextEdit()
        self.grammar.setPlaceholderText("S -> A b | c\nA -> a | ε")
        self.grammar.setPlainText("E -> E + T | T\nT -> T * F | F\nF -> ( E ) | id")
        self.input = QPlainTextEdit()
        self.input.setMaximumHeight(42)
        self.input.setPlainText("id + id * id")
        top.addWidget(QLabel("Input:"))
        top.addWidget(self.input)
        layout.addLayout(top)
        split = QSplitter()
        split.addWidget(self.grammar)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        split.addWidget(self.output)
        layout.addWidget(split, 1)
        actions = QHBoxLayout()
        for label, callback in (
            ("FIRST / FOLLOW", self.first_follow), ("LL(1) Table", self.ll1),
            ("Predictive Parse", self.predict), ("Remove Left Recursion", self.no_left_rec),
            ("Left Factoring", self.factor), ("Shift / Reduce", self.shift_reduce),
            ("LR(0) / SLR(1)", self.slr),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _run(self, fn) -> None:
        try:
            grammar = core.Grammar.parse(self.grammar.toPlainText())
            self.output.setPlainText(fn(grammar))
        except Exception as exc:
            self.output.setPlainText(f"Grammar error: {exc}")

    def first_follow(self) -> None:
        def run(grammar):
            result = core.FirstFollow(grammar)
            return "FIRST / FOLLOW\n" + "\n".join(
                f"{name}: FIRST={{{', '.join(sorted(result.first[name]))}}}  "
                f"FOLLOW={{{', '.join(sorted(result.follow[name]))}}}"
                for name in grammar.rules
            )
        self._run(run)

    def ll1(self) -> None:
        self._run(lambda grammar: core.LL1Table(grammar).text())

    def predict(self) -> None:
        def run(grammar):
            _, trace, message = core.predictive_parse(core.LL1Table(grammar), self.input.toPlainText())
            return message + "\n\nSTEP\tSTACK\tINPUT\tACTION\n" + "\n".join(
                f"{i + 1}\t{stack}\t{source}\t{action}"
                for i, (stack, source, action) in enumerate(trace)
            )
        self._run(run)

    def no_left_rec(self) -> None:
        self._run(lambda grammar: "Grammar after removing left recursion:\n" + core.remove_left_recursion(grammar).format())

    def factor(self) -> None:
        self._run(lambda grammar: "Grammar after left factoring:\n" + core.left_factor(grammar).format())

    def shift_reduce(self) -> None:
        def run(grammar):
            _, trace, message = core.shift_reduce_parse(grammar, self.input.toPlainText())
            return message + "\n" + "\n".join(trace)
        self._run(run)

    def slr(self) -> None:
        self._run(core.slr_report)


class EasyLangQt(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EasyLang Studio")
        self.setMinimumSize(900, 600)
        self.settings = QSettings("EasyLang", "EasyLang Studio")
        self.theme_manager = ThemeManager()
        self.theme_name = str(self.settings.value("appearance/theme", "Dark+"))
        self.docs: dict[CodeEditor, dict[str, object]] = {}
        self.workspace_root: Path | None = None
        self._worker: CompileWorker | None = None
        self._worker_editor: CodeEditor | None = None
        self._last_compile_editor: CodeEditor | None = None
        self._build_actions()
        self._build_editor()
        self._build_docks()
        self._build_toolbar()
        self._build_menus()
        self.status = StudioStatusBar(self)
        self.setStatusBar(self.status)
        self.language.currentTextChanged.connect(self.status.set_language)
        self._build_palette()
        if not self.restoreGeometry(self.settings.value("window/geometry", b"")):
            self.resize(1500, 920)
        state = self.settings.value("window/state")
        if state:
            self.restoreState(state)
        last_folder = str(self.settings.value("workspace/lastFolder", ""))
        if last_folder and Path(last_folder).is_dir():
            self._set_workspace(last_folder)
        saved_files = self.settings.value("files/open", [])
        if isinstance(saved_files, str):
            saved_files = [saved_files]
        if not isinstance(saved_files, (list, tuple)):
            saved_files = []
        opened_files = [Path(path) for path in saved_files if Path(path).is_file()]
        for path in opened_files:
            self.open_path(path)
        if not opened_files:
            self.new_file(initial=True)
        self.apply_theme(self.theme_name)

    def _add_action(self, name: str, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        self.actions[name] = action
        return action

    def _build_actions(self) -> None:
        self.actions: dict[str, QAction] = {}
        self._add_action("new", "New File", self.new_file, "Ctrl+N")
        self._add_action("open", "Open File...", self.open_file, "Ctrl+O")
        self._add_action("workspace", "Open Project Folder...", self.open_workspace, "Ctrl+K, Ctrl+O")
        self._add_action("save", "Save", self.save_file, "Ctrl+S")
        self._add_action("save_as", "Save As...", self.save_as, "Ctrl+Shift+S")
        self._add_action("close_tab", "Close Editor", self._close_current_tab, "Ctrl+W")
        self._add_action("next_tab", "Switch Editor", self._next_tab, "Ctrl+Tab")
        self._add_action("compile", "Compile", lambda: self.compile(False), "F9")
        self._add_action("run", "Run", lambda: self.compile(True), "F5")
        self._add_action("debug", "Start Debugging", self.debug, "Ctrl+F5")
        self._add_action("stop", "Stop", self.stop_execution, "Shift+F5")
        self._add_action("theme", "Toggle Theme", self.toggle_theme)
        self._add_action("grammar", "Grammar Workbench", self.open_grammar)
        self._add_action("correct", "Auto Correction", self.auto_correct)
        self._add_action("find", "Find", self.find, "Ctrl+F")
        self._add_action("replace", "Replace", self.replace, "Ctrl+H")
        self._add_action("goto_line", "Go to Line...", self.go_to_line, "Ctrl+G")
        self._add_action("comment", "Toggle Line Comment", self.toggle_comment, "Ctrl+/")
        self._add_action("duplicate_line", "Duplicate Line", self.duplicate_line, "Shift+Alt+Down")
        self._add_action("toggle_explorer", "Toggle Explorer", self._toggle_explorer, "Ctrl+B")
        self._add_action("toggle_output", "Toggle Compiler Output", self._toggle_output, "Ctrl+J")
        self._add_action("visual_workspace", "Visual Compiler Workspace", self.open_visual_workspace, "F7")
        self._add_action("palette", "Show Command Palette", self.show_command_palette, "Ctrl+Shift+P")
        self._add_action("undo", "Undo", self._undo, "Ctrl+Z")
        self._add_action("redo", "Redo", self._redo, "Ctrl+Y")
        self._add_action("exit", "Exit", self.close)
        self._add_action("about", "About EasyLang Studio", self._about)

    def _build_editor(self) -> None:
        self.editors = QTabWidget(self)
        self.editors.setTabsClosable(True)
        self.editors.setMovable(True)
        self.editors.tabCloseRequested.connect(self.close_tab)
        self.editors.currentChanged.connect(lambda _index: self._cursor_status())
        self.setCentralWidget(self.editors)

    def _build_docks(self) -> None:
        self.explorer = ExplorerWidget(self)
        self.explorer.fileActivated.connect(self._explorer_open)
        self.explorer.openFolderRequested.connect(self.open_workspace)
        self.explorer_dock = QDockWidget("EXPLORER", self)
        self.explorer_dock.setObjectName("ExplorerDock")
        self.explorer_dock.setMinimumWidth(210)
        self.explorer_dock.setWidget(self.explorer)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.explorer_dock)

        self.output_panel = OutputPanel(self)
        self.output_panel.lineRequested.connect(self._goto_line)
        self.output_panel.sourceLineSelected.connect(self._select_source_line)
        self.output_dock = QDockWidget("COMPILER OUTPUT & VISUAL COMPILER WORKSPACE", self)
        self.output_dock.setObjectName("CompilerOutputDock")
        self.output_dock.setMinimumHeight(170)
        self.output_dock.setWidget(self.output_panel)
        self.output_panel.debugCommand.connect(self._debug_command)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.output_dock)

        self.activity_dock = QDockWidget(self)
        self.activity_dock.setObjectName("ActivityBarDock")
        self.activity_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.activity_dock.setTitleBarWidget(QWidget(self.activity_dock))
        activity = QWidget(self.activity_dock)
        activity.setFixedWidth(48)
        activity.setObjectName("ActivityBar")
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(2, 6, 2, 6)
        activity_layout.setSpacing(3)
        self._activity_button(activity_layout, "Explorer", QStyleIcon(QStyle.StandardPixmap.SP_DirOpenIcon), self.actions["toggle_explorer"])
        self._activity_button(activity_layout, "Search", QStyleIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), self.actions["find"])
        self._activity_button(activity_layout, "Run / Debug", _action_icon("debug"), self.actions["debug"])
        self._activity_button(activity_layout, "Grammar Workbench", QStyleIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), self.actions["grammar"])
        activity_layout.addStretch(1)
        self._activity_button(activity_layout, "Settings / Toggle Theme", QStyleIcon(QStyle.StandardPixmap.SP_FileDialogInfoView), self.actions["theme"])
        self.activity_dock.setWidget(activity)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.activity_dock)
        self.splitDockWidget(self.activity_dock, self.explorer_dock, Qt.Orientation.Horizontal)
        self.resizeDocks([self.activity_dock, self.explorer_dock], [48, 260], Qt.Orientation.Horizontal)

    def _activity_button(self, layout: QVBoxLayout, tooltip: str, icon: QIcon, action: QAction) -> None:
        button = QToolButton(self)
        action.setIcon(icon)
        button.setDefaultAction(action)
        button.setToolTip(tooltip)
        button.setFixedSize(40, 40)
        layout.addWidget(button)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Run", self)
        toolbar.setObjectName("RunToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(toolbar)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for name, shortcut in (
            ("new", "Ctrl+N"), ("open", "Ctrl+O"), ("save", "Ctrl+S"),
            ("run", "F5"), ("debug", "Ctrl+F5"), ("stop", "Shift+F5"), ("compile", "F9"),
            ("visual_workspace", "F7"), ("correct", "Auto Fix"),
        ):
            action = self.actions[name]
            action.setIcon(_action_icon(name if name in {"run", "debug", "stop", "compile"} else "correct" if name == "correct" else "compile"))
            action.setToolTip(f"{action.text()} ({shortcut})")
            toolbar.addAction(action)
            toolbutton = toolbar.widgetForAction(action)
            if toolbutton is not None:
                object_names = {"run": "RunActionButton", "debug": "DebugActionButton", "stop": "StopActionButton", "visual_workspace": "VisualActionButton", "correct": "SafeFixActionButton"}
                toolbutton.setObjectName(object_names.get(name, "ToolbarActionButton"))
        toolbar.addSeparator()
        self.language = QComboBox(self)
        self.language.addItems(["EasyLang", "C++17"])
        self.language.setToolTip("Select source language for compilation")
        toolbar.addWidget(self.language)

    def _build_menus(self) -> None:
        menus = {name: self.menuBar().addMenu(f"&{name}") for name in ("File", "Edit", "View", "Run", "Tools", "Help")}
        for name in ("new", "open", "workspace", "save", "save_as", "close_tab"):
            menus["File"].addAction(self.actions[name])
        menus["File"].addSeparator()
        menus["File"].addAction(self.actions["exit"])
        for name in ("find", "replace", "goto_line", "comment", "duplicate_line", "next_tab"):
            menus["Edit"].addAction(self.actions[name])
        menus["Edit"].addSeparator()
        menus["Edit"].addAction(self.actions["undo"])
        menus["Edit"].addAction(self.actions["redo"])
        menus["View"].addAction(self.actions["toggle_explorer"])
        menus["View"].addAction(self.actions["toggle_output"])
        menus["View"].addAction(self.actions["visual_workspace"])
        menus["View"].addAction(self.actions["theme"])
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        themes = menus["View"].addMenu("Color Theme")
        self.theme_actions: dict[str, QAction] = {}
        for theme_name in THEMES:
            action = QAction(theme_name, self, checkable=True)
            action.triggered.connect(lambda checked=False, name=theme_name: self.apply_theme(name))
            self.theme_group.addAction(action)
            themes.addAction(action)
            self.theme_actions[theme_name] = action
        for name in ("compile", "run", "debug", "stop"):
            menus["Run"].addAction(self.actions[name])
        for name in ("correct", "grammar"):
            menus["Tools"].addAction(self.actions[name])
        menus["Help"].addAction(self.actions["about"])
        menus["Help"].addAction(self.actions["palette"])

    def _build_palette(self) -> None:
        palette_actions = list(self.actions.values()) + list(self.theme_actions.values())
        palette_actions.extend((self.explorer_dock.toggleViewAction(), self.output_dock.toggleViewAction()))
        self.command_palette = CommandPalette(palette_actions, self)

    def editor(self) -> CodeEditor | None:
        widget = self.editors.currentWidget()
        return widget if isinstance(widget, CodeEditor) else None

    def new_file(self, _checked: bool = False, initial: bool = False) -> None:
        editor = CodeEditor(self)
        if initial:
            editor.setPlainText(core.SAMPLE)
        self._register_editor(editor, None)
        index = self.editors.addTab(editor, "Untitled")
        self.editors.setCurrentIndex(index)
        self._refresh_tab_colors()
        self.status.set_compile_status(0)
        self._cursor_status()

    def _register_editor(self, editor: CodeEditor, path: str | None) -> None:
        self.docs[editor] = {
            "path": path, "modified": False, "saved_text": editor.toPlainText(),
        }
        editor.textChanged.connect(lambda e=editor: self._mark_modified(e))
        editor.cursorPositionChanged.connect(self._cursor_status)

    def _mark_modified(self, editor: CodeEditor) -> None:
        data = self.docs.get(editor)
        if data is None:
            return
        data["modified"] = editor.toPlainText() != data["saved_text"]
        index = self.editors.indexOf(editor)
        if index >= 0:
            path = data["path"]
            title = Path(str(path)).name if path else "Untitled"
            self.editors.setTabText(index, f"● {title}" if data["modified"] else title)
            self.editors.tabBar().setTabTextColor(
                index,
                QColor(THEMES[self.theme_name]["modified"] if data["modified"] else THEMES[self.theme_name]["text"]),
            )

    def open_workspace(self, _checked: bool = False) -> None:
        start = str(self.workspace_root or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Open project folder", start)
        if folder:
            self._set_workspace(folder)

    def _set_workspace(self, folder: str) -> None:
        self.workspace_root = Path(folder).resolve()
        self.explorer.set_root(str(self.workspace_root))
        self.explorer_dock.setWindowTitle(f"EXPLORER - {self.workspace_root.name or self.workspace_root}")
        self.settings.setValue("workspace/lastFolder", str(self.workspace_root))
        self.status.showMessage(f"Workspace: {self.workspace_root}", 4000)

    def _explorer_open(self, path: str) -> None:
        self.open_path(Path(path))

    def open_file(self, _checked: bool = False) -> None:
        start = str(self.workspace_root or Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Open source file", start, SOURCE_FILTER)
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        path = path.resolve()
        for editor, data in self.docs.items():
            if data["path"] and Path(str(data["path"])).resolve() == path:
                self.editors.setCurrentWidget(editor)
                return
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        editor = CodeEditor(self)
        editor.setPlainText(content)
        self._register_editor(editor, str(path))
        self.editors.addTab(editor, path.name)
        self._refresh_tab_colors()
        self.editors.setCurrentWidget(editor)
        self._cursor_status()

    def save_file(self, _checked: bool = False) -> bool:
        editor = self.editor()
        return self._save_editor(editor) if editor is not None else False

    def _save_editor(self, editor: CodeEditor) -> bool:
        path = self.docs[editor]["path"]
        if not path:
            return self._save_editor_as(editor)
        try:
            Path(str(path)).write_text(editor.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self.docs[editor]["modified"] = False
        self.docs[editor]["saved_text"] = editor.toPlainText()
        index = self.editors.indexOf(editor)
        self.editors.setTabText(index, Path(str(path)).name)
        self.editors.tabBar().setTabTextColor(index, QColor(THEMES[self.theme_name]["text"]))
        self.status.showMessage(f"Saved {path}", 3000)
        return True

    def save_as(self, _checked: bool = False) -> bool:
        editor = self.editor()
        return self._save_editor_as(editor) if editor is not None else False

    def _save_editor_as(self, editor: CodeEditor) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save source file", "program.easy",
            "EasyLang (*.el *.easy *.txt);;C++ (*.cpp);;All files (*)",
        )
        if not path:
            return False
        self.docs[editor]["path"] = path
        return self._save_editor(editor)

    def close_tab(self, index: int) -> None:
        editor = self.editors.widget(index)
        if editor is None:
            return
        if self.docs.get(editor, {}).get("modified"):
            answer = QMessageBox.question(
                self, "Save changes?", f"Save changes to {self.editors.tabText(index).lstrip('● ')}?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save:
                self.editors.setCurrentWidget(editor)
                if not self._save_editor(editor):
                    return
        self.docs.pop(editor, None)
        self.editors.removeTab(index)
        editor.deleteLater()
        if self.editors.count() == 0:
            self.new_file()

    def _close_current_tab(self, _checked: bool = False) -> None:
        self.close_tab(self.editors.currentIndex())

    def _next_tab(self, _checked: bool = False) -> None:
        count = self.editors.count()
        if count > 1:
            self.editors.setCurrentIndex((self.editors.currentIndex() + 1) % count)

    def _put(self, name: str, text: object) -> None:
        self.output_panel.set_output(name, str(text))

    def compile(self, run: bool = False) -> None:
        editor = self.editor()
        if editor is None:
            return
        if self._worker is not None and self._worker.isRunning():
            self.status.showMessage("A compile or execution is already in progress")
            return
        self.output_panel.clear()
        self.status.set_compile_status(0)
        editor.set_error_location(None)
        data = self.docs[editor]
        self._last_compile_editor = editor
        self._start_worker(editor.toPlainText(), data["path"], run, False)

    def debug(self, _checked: bool = False) -> None:
        editor = self.editor()
        if editor is None:
            return
        if self._worker is not None and self._worker.isRunning():
            self.status.showMessage("A compile or execution is already in progress")
            return
        self.output_panel.clear()
        self.status.set_compile_status(0)
        editor.set_error_location(None)
        self._last_compile_editor = editor
        self.output_panel.select("Debugger")
        self._start_worker(editor.toPlainText(), self.docs[editor]["path"], True, True)

    def _start_worker(self, source: str, path: str | None, run: bool, debug: bool) -> None:
        worker = CompileWorker(source, path, self.language.currentText(), run, debug, self)
        worker.completed.connect(self._compile_completed)
        worker.stageChanged.connect(self._pipeline_stage_changed)
        worker.visualizationReady.connect(self._visualization_ready)
        worker.statement.connect(self._debug_statement)
        worker.finished.connect(lambda current=worker: self._worker_finished(current))
        self._worker = worker
        self._worker_editor = self._last_compile_editor
        self.status.showMessage("Compiling..." if not run else "Running...")
        worker.start()

    def _pipeline_stage_changed(self, stages: list[dict]) -> None:
        self.output_panel.set_pipeline(stages)

    def _visualization_ready(self, program, graph) -> None:
        self.output_panel.set_ast(program)
        self.output_panel.set_cfg(graph)

    def _compile_completed(self, result: dict[str, object]) -> None:
        outputs = result["outputs"]
        self.output_panel.set_pipeline(result.get("pipeline", []))
        cfg_error = result.get("visualization_error")
        if result.get("cfg") is None and result.get("program") is None and result.get("error") is not None:
            cfg_error = f"CFG unavailable because the parser did not produce an AST: {result['error']}"
        self.output_panel.set_cfg(result.get("cfg"), cfg_error)
        for name, text in outputs.items():
            if name not in ("AST", "Tokens", "Symbol Table", "Three Address Code", "Debugger"):
                self._put(name, text)
        # Populate the C++ visualization panels for C++ sources. These views use
        # Clang where available and clearly labeled source-based approximations otherwise.
        source_editor_for_visuals = self._worker_editor
        source_path_for_visuals = self.docs.get(source_editor_for_visuals, {}).get("path") if source_editor_for_visuals else None
        is_cpp_for_visuals = self.language.currentText() == "C++17" or (
            source_path_for_visuals and Path(str(source_path_for_visuals)).suffix.lower() in {".cpp", ".cc", ".cxx", ".h", ".hpp"}
        )
        if is_cpp_for_visuals and source_editor_for_visuals is not None:
            try:
                cpp_data = analyze_cpp(source_editor_for_visuals.toPlainText(), source_path_for_visuals)
                cpp_tokens = [SimpleNamespace(**token) for token in cpp_data.get("tokens", [])]
                self.output_panel.set_tokens(cpp_tokens)
                self.output_panel.set_cpp_ast(cpp_data.get("ast_tree") or {})
                self.output_panel.set_symbols({item["name"]: item for item in cpp_data.get("symbols", [])})
                self.output_panel.set_cfg(cpp_data.get("cfg"), "C++ source-based CFG (approximate; branches/loops are heuristic).")
                self._put("Three Address Code", cpp_data.get("ir", "LLVM IR unavailable"))
            except Exception as cpp_visual_error:
                self._put("Errors", f"C++ visualization failed: {cpp_visual_error}")
        if result.get("tokens"):
            self.output_panel.set_tokens(result["tokens"])
        if result.get("program") is not None:
            self.output_panel.set_ast(result["program"])
        if result.get("symbols"):
            self.output_panel.set_symbols(result["symbols"])
            self.output_panel.views["Debugger"].set_values(
                result["values"] if "values" in result else {},
                {name: item["type"] for name, item in result["symbols"].items()},
            )
        if result.get("tac"):
            self.output_panel.set_tac(result["tac"], result.get("tac_source_map"))
        if "Debugger" in outputs:
            self.output_panel.views["Debugger"].set_summary(outputs["Debugger"])
        error = result["error"]
        if error is not None:
            error_text = str(error)
            errors = error.errors if isinstance(error, core.CompilerErrors) else [error]
            source_editor = self._worker_editor
            if source_editor is not None:
                source_path = self.docs.get(source_editor, {}).get("path")
                is_cpp_source = self.language.currentText() == "C++17" or (
                    source_path and Path(str(source_path)).suffix.lower() in {".cpp", ".cc", ".cxx"}
                )
                if is_cpp_source:
                    cpp_fixes = CppSafeFixer(source_editor.toPlainText()).suggestions()
                    if cpp_fixes:
                        error_text += "\n\nC++ Safe Fix suggestions (preview before applying):\n" + "\n".join(
                            f"Line {line}: {description} -> {replacement}" for line, description, replacement in cpp_fixes
                        )
                    else:
                        error_text += "\n\nNo high-confidence mechanical C++ fix was detected. Review compiler diagnostics manually."
                else:
                    corrector = core.AutoCorrector(source_editor.toPlainText())
                    suggestions = corrector.suggestions_for_error(error)
                    if suggestions:
                        error_text += "\n\nSafe fix suggestions (review before applying):\n" + "\n".join(
                            f"Line {line}: {description} -> {replacement}"
                            for line, description, replacement in suggestions
                        )
                    else:
                        error_text += "\n\nNo unambiguous automatic safe fix was found for this diagnostic."
            self._put("Errors", error_text)
            self.output_panel.select("Errors")
            self.status.set_compile_status(len(errors))
            self.status.showMessage("Compilation/debugging failed")
            if errors and source_editor is not None and hasattr(errors[0], "line"):
                line = errors[0].line
                column = getattr(errors[0], "column", 1)
                source_editor.set_error_location(line, column)
                self._select_source_line(line, column)
            return
        editor = self._worker_editor
        if editor is not None:
            editor.set_error_location(None)
        self.status.set_compile_status(0)
        self.status.showMessage(str(result["status"]))
        if "Debugger" in outputs:
            self.output_panel.select("Debugger")
        elif "Output" in outputs:
            self.output_panel.select("Output")
        else:
            self.output_panel.select("Compilation Pipeline")

    def _worker_finished(self, worker: CompileWorker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()

    def stop_execution(self, _checked: bool = False) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            self.status.showMessage("Stopping execution...")
        else:
            self.status.showMessage("No active execution to stop", 2500)

    def _debug_command(self, command: str) -> None:
        if command == "start":
            self.debug()
            return
        worker = self._worker
        if worker is None or not worker.isRunning():
            return
        if command == "pause":
            worker.pause_execution()
        elif command == "step":
            worker.step_once()
        elif command == "continue":
            worker.continue_execution()
        elif command == "stop":
            self.stop_execution()

    def _debug_statement(self, line: int, values: dict, kind: str) -> None:
        types = self._worker.symbol_types if self._worker is not None else {}
        self.output_panel.set_debug_state(line, kind, values, types)
        self.output_panel.highlight_source_line(line)
        editor = self._worker_editor
        if editor is not None:
            block = editor.document().findBlockByNumber(max(0, line - 1))
            if block.isValid():
                self._select_source_line(line)

    def auto_correct(self, _checked: bool = False) -> None:
        editor = self.editor()
        if editor is None:
            return
        source_path = self.docs.get(editor, {}).get("path")
        is_cpp = self.language.currentText() == "C++17" or (
            source_path and Path(str(source_path)).suffix.lower() in {".cpp", ".cc", ".cxx", ".h", ".hpp"}
        )
        corrector = CppSafeFixer(editor.toPlainText()) if is_cpp else core.AutoCorrector(editor.toPlainText())
        fixes = corrector.suggestions()
        if not fixes:
            QMessageBox.information(self, "Auto Correction", "No obvious safe corrections found.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Auto Correction")
        dialog.resize(680, 420)
        layout = QVBoxLayout(dialog)
        listing = QPlainTextEdit()
        listing.setReadOnly(True)
        listing.setPlainText("\n".join(f"Line {line}: {desc} -> {new}" for line, desc, new in fixes))
        if is_cpp:
            listing.appendPlainText("\nThese are conservative suggestions. Compiler-specific and semantic errors may require manual correction.")
        layout.addWidget(listing)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            lambda: (editor.setPlainText(corrector.apply()), dialog.accept())
        )
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def find(self, _checked: bool = False) -> None:
        query, ok = QInputDialog.getText(self, "Find", "Find text:")
        if not ok or not query:
            return
        editor = self.editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        found = editor.document().find(query, cursor)
        if found.isNull():
            found = editor.document().find(query)
        if not found.isNull():
            editor.setTextCursor(found)
            editor.setFocus()
        else:
            self.status.showMessage("Text not found", 2500)

    def replace(self, _checked: bool = False) -> None:
        query, ok = QInputDialog.getText(self, "Replace", "Find text:")
        if not ok or not query:
            return
        replacement, ok = QInputDialog.getText(self, "Replace", "Replace with:")
        if not ok:
            return
        editor = self.editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(editor.toPlainText().replace(query, replacement))
        self.status.showMessage("Replace completed", 2500)

    def go_to_line(self, _checked: bool = False) -> None:
        editor = self.editor()
        if editor is None:
            return
        line, accepted = QInputDialog.getInt(
            self, "Go to Line", "Line number:", 1, 1, max(1, editor.blockCount())
        )
        if accepted:
            self._select_source_line(line)

    def toggle_comment(self, _checked: bool = False) -> None:
        editor = self.editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        first = editor.document().findBlock(start)
        last = editor.document().findBlock(end)
        if cursor.hasSelection() and end == last.position() and last != first:
            last = last.previous()
        blocks = []
        block = first
        while block.isValid():
            blocks.append(block)
            if block == last:
                break
            block = block.next()
        if not blocks:
            return
        uncomment = all(block.text().lstrip().startswith("//") for block in blocks)
        for block in reversed(blocks):
            text = block.text()
            indent = len(text) - len(text.lstrip())
            edit = editor.textCursor()
            edit.setPosition(block.position() + indent)
            if uncomment:
                edit.movePosition(QTextCursor.MoveOperation.NextCharacter)
                edit.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
                if text[indent + 2:indent + 3] == " ":
                    edit.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
                edit.removeSelectedText()
            else:
                edit.insertText("// ")

    def duplicate_line(self, _checked: bool = False) -> None:
        editor = self.editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        start = editor.document().findBlock(cursor.selectionStart())
        end = editor.document().findBlock(cursor.selectionEnd())
        if cursor.hasSelection() and cursor.selectionEnd() == end.position() and end != start:
            end = end.previous()
        lines = []
        block = start
        while block.isValid():
            lines.append(block.text())
            if block == end:
                break
            block = block.next()
        text = "\n".join(lines)
        insert = editor.textCursor()
        insert.setPosition(end.position())
        insert.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        insert.insertText("\n" + text)

    def open_grammar(self, _checked: bool = False) -> None:
        dialog = GrammarDialog(self)
        dialog.exec()

    def toggle_theme(self, _checked: bool = False) -> None:
        self.apply_theme("Light+" if self.theme_name == "Dark+" else "Dark+")

    def apply_theme(self, theme_name: str) -> None:
        app = QApplication.instance()
        self.theme_name = self.theme_manager.apply(app, theme_name)
        self.settings.setValue("appearance/theme", self.theme_name)
        for editor in self.docs:
            editor.set_theme(self.theme_name)
        self._refresh_tab_colors()
        self.output_panel.set_theme(self.theme_name)
        for name, action in self.theme_actions.items():
            action.setChecked(name == self.theme_name)
        self._cursor_status()

    def _refresh_tab_colors(self) -> None:
        tab_bar = self.editors.tabBar()
        colors = THEMES[self.theme_name]
        for index in range(self.editors.count()):
            editor = self.editors.widget(index)
            modified = self.docs.get(editor, {}).get("modified", False)
            color = colors["modified"] if modified else colors["text"]
            tab_bar.setTabTextColor(index, QColor(color))

    def show_command_palette(self, _checked: bool = False) -> None:
        self.command_palette.open()

    def _toggle_explorer(self, _checked: bool = False) -> None:
        self.explorer_dock.setVisible(not self.explorer_dock.isVisible())

    def _toggle_output(self, _checked: bool = False) -> None:
        self.output_dock.setVisible(not self.output_dock.isVisible())

    def open_visual_workspace(self, _checked: bool = False) -> None:
        self.output_dock.show()
        self.output_panel.select("Compilation Pipeline")
        self.status.showMessage("Visual Compiler Workspace", 2500)

    def _goto_line(self, line: int, column: int = 1) -> None:
        editor = self._last_compile_editor or self.editor()
        if editor is None:
            return
        block = editor.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            self.output_dock.show()
            cursor = editor.textCursor()
            cursor.setPosition(block.position() + min(max(column - 1, 0), len(block.text())))
            editor.setTextCursor(cursor)
            editor.set_error_location(line, column)
            editor.setFocus()

    def _select_source_line(self, line: int, column: int = 1) -> None:
        editor = self._last_compile_editor or self.editor()
        if editor is None:
            return
        block = editor.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            cursor = editor.textCursor()
            cursor.setPosition(block.position() + min(max(column - 1, 0), len(block.text())))
            editor.setTextCursor(cursor)
            editor.setFocus()

    def _cursor_status(self) -> None:
        editor = self.editor()
        if editor is not None:
            cursor = editor.textCursor()
            self.status.set_position(cursor.blockNumber() + 1, cursor.positionInBlock() + 1)

    def _undo(self) -> None:
        editor = self.editor()
        if editor is not None:
            editor.undo()

    def _redo(self) -> None:
        editor = self.editor()
        if editor is not None:
            editor.redo()

    def _about(self) -> None:
        QMessageBox.about(self, "About EasyLang Studio", "EasyLang Studio\nCompiler IDE built with PySide6.")

    def closeEvent(self, event) -> None:
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            if not worker.wait(2000):
                self.status.showMessage("Waiting for the active execution to stop")
                event.ignore()
                return
        for editor, data in list(self.docs.items()):
            if not data.get("modified"):
                continue
            answer = QMessageBox.question(
                self, "Save changes?", f"Save changes to {self.editors.tabText(self.editors.indexOf(editor)).lstrip('● ')}?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Save:
                self.editors.setCurrentWidget(editor)
                if not self._save_editor(editor):
                    event.ignore()
                    return
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue(
            "files/open",
            [str(data["path"]) for data in self.docs.values() if data["path"]],
        )
        if self.workspace_root:
            self.settings.setValue("workspace/lastFolder", str(self.workspace_root))
        event.accept()


def QStyleIcon(name: QStyle.StandardPixmap) -> QIcon:
    return QApplication.style().standardIcon(name)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("EasyLang Studio")
    app.setFont(QFont("Segoe UI", 10))
    window = EasyLangQt()
    window.show()
    sys.exit(app.exec())
