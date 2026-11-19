import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main_window import EasyLangQt
from theme_manager import THEMES


class EasyLangGuiSmokeTests(unittest.TestCase):
    settings_keys = (
        "files/open",
        "workspace/lastFolder",
        "window/geometry",
        "window/state",
        "appearance/theme",
    )

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = QSettings("EasyLang", "EasyLang Studio")
        self.saved_settings = {
            key: (self.settings.contains(key), self.settings.value(key))
            for key in self.settings_keys
        }
        for key in self.settings_keys:
            self.settings.remove(key)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project = Path(self.temp_dir.name)
        self.source = self.project / "smoke.easy"
        self.source.write_text("START\nint value = 7;\nprint(value);\nEND\n", encoding="utf-8")
        self.window = EasyLangQt()

    def tearDown(self):
        if self.window is not None:
            with patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard
            ):
                self.window.close()
        self.temp_dir.cleanup()
        for key, (was_present, value) in self.saved_settings.items():
            if was_present:
                self.settings.setValue(key, value)
            else:
                self.settings.remove(key)

    def wait_for_worker(self, timeout=10):
        deadline = time.monotonic() + timeout
        while self.window._worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertIsNone(self.window._worker, "compiler worker did not finish")

    def test_workspace_open_compile_run_and_output_tabs(self):
        self.window._set_workspace(str(self.project))
        self.assertEqual(self.window.workspace_root, self.project.resolve())
        initial_tabs = self.window.editors.count()
        self.window.open_path(self.source)
        editor = self.window.editor()
        self.assertEqual(editor.toPlainText(), self.source.read_text(encoding="utf-8"))
        self.assertEqual(self.window.editors.count(), initial_tabs + 1)

        self.window.compile()
        self.wait_for_worker()
        self.assertEqual(self.window.status.compile_status.text(), "No errors")
        self.window.compile(run=True)
        self.wait_for_worker()
        self.assertIn("7", self.window.output_panel.views["Output"].toPlainText())

        expected_tabs = (
            "Output",
            "Errors",
            "Tokens",
            "AST",
            "Symbol Table",
            "Three Address Code",
            "Debugger",
        )
        self.assertEqual(tuple(self.window.output_panel.views), expected_tabs)
        for name in expected_tabs:
            self.window.output_panel.select(name)
            self.assertIs(
                self.window.output_panel.tabs.currentWidget(),
                self.window.output_panel.views[name],
            )

    def test_duplicate_file_open_focuses_existing_editor(self):
        initial_tabs = self.window.editors.count()
        self.window.open_path(self.source)
        editor = self.window.editor()
        opened_tabs = self.window.editors.count()
        self.window.open_path(self.source)
        self.assertEqual(opened_tabs, initial_tabs + 1)
        self.assertEqual(self.window.editors.count(), opened_tabs)
        self.assertIs(self.window.editor(), editor)

    def test_error_click_navigates_to_underlined_source(self):
        self.window.open_path(self.source)
        editor = self.window.editor()
        editor.setPlainText("START\nprint(missing);\nEND")
        self.window.compile()
        self.wait_for_worker()
        self.assertEqual(self.window.status.compile_status.text(), "1 errors")
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        self.window.output_panel._activate_error(self.window.output_panel.errors.item(0))
        self.assertEqual(editor.textCursor().blockNumber(), 1)
        self.assertEqual(editor.error_location[0], 2)
        self.assertTrue(any(selection.format.underlineStyle() for selection in editor.extraSelections()))

    def test_auto_correction_suggestion_and_editor_tab_colors(self):
        editor = self.window.editor()
        editor.clear()
        QTest.keyClicks(editor, "prnt")
        self.assertEqual(editor.correction_suggestion, (0, 4, "print"))
        QTest.keyClick(editor, Qt.Key.Key_Period, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.toPlainText(), "print")
        editor.clear()
        QTest.keyClicks(editor, "prnt(")
        self.assertEqual(editor.correction_suggestion, (0, 4, "print"))
        QTest.keyClick(editor, Qt.Key.Key_Period, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.toPlainText(), "print()")
        editor.clear()
        statement = "int count = 4"
        QTest.keyClicks(editor, statement)
        self.assertEqual(editor.correction_suggestion, (len(statement), len(statement), ";"))
        QTest.keyClick(editor, Qt.Key.Key_Period, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(editor.toPlainText(), statement + ";")

        editor.setPlainText("START\nprint(value);\nEND")
        tab_bar = self.window.editors.tabBar()
        self.assertEqual(tab_bar.tabTextColor(0).name(), THEMES["Dark+"]["modified"])
        formats = editor.document().firstBlock().layout().formats()
        self.assertTrue(any(
            item.format.foreground().color().name() == THEMES["Dark+"]["keyword"]
            for item in formats
        ))
        self.assertEqual(
            editor.palette().color(QPalette.ColorRole.Text).name(),
            THEMES["Dark+"]["text"],
        )

        self.window.new_file()
        self.assertEqual(tab_bar.tabTextColor(1).name(), THEMES["Dark+"]["text"])
        self.window.apply_theme("Light+")
        self.assertEqual(tab_bar.tabTextColor(0).name(), THEMES["Light+"]["modified"])
        self.assertEqual(tab_bar.tabTextColor(1).name(), THEMES["Light+"]["text"])
        self.assertEqual(
            editor.palette().color(QPalette.ColorRole.Text).name(),
            THEMES["Light+"]["text"],
        )


if __name__ == "__main__":
    unittest.main()
