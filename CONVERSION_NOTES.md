# Java-to-Python conversion inventory

| Java source | Python destination |
|---|---|
| `src/Main.java` | `easylang_studio.py` compiler core, AST, lexer/parser, semantics, TAC, interpreter and main window |
| `src/GrammarTools.java` | `easylang_studio.py` grammar parser, FIRST/FOLLOW, LL(1), predictive parse, left recursion/factoring, shift-reduce, LR(0)/SLR |
| `src/CppSupport.java` | `cpp_run()` in `easylang_studio.py` |
| `src/AdvancedToolsGUI.java` | Advanced grammar-lab tab in `EasyLangStudio` |
| `src/EasyLangStudio.java` | Historical Tkinter IDE shell; the current supported desktop launcher is the modular PySide6 application (`run.py` → `easylang_qt.py` → `main_window.py`) |
| `src/StudioTheme.java` | Tk/ttk dark and light theme setup |

The conversion is a Python reimplementation, not mechanical line-for-line translation. Swing widgets and delegates were replaced with Tkinter/ttk equivalents. See README.md for known differences and requirements.


## Current desktop application note

The conversion inventory above preserves historical conversion context. The
active desktop entry point in this repository is PySide6, not the legacy Tkinter
class still present in `easylang_studio.py`. The active Qt application modules
are `run.py`, `easylang_qt.py`, `main_window.py`, `editor.py`, `explorer.py`,
`output_panel.py`, `highlighter.py`, `theme_manager.py`, and `status_bar.py`.
