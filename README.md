# EasyLang Studio — Python Edition

A Python port of the supplied Java EasyLang compiler project, now with a modern
PySide6 desktop interface inspired by professional IDEs such as Visual Studio Code.

## Requirements
- Python 3.10 or newer
- PySide6 (installed by the launch scripts or with `python -m pip install -r requirements.txt`)
- Optional: GCC `g++` for C++17 compilation

## Run
Windows: double-click `run.bat`, or run `python run.py`.
Linux/macOS: run `chmod +x run.sh && ./run.sh` or `python3 run.py`.

The PySide6 interface is launched through `run.py` and `easylang_qt.py`, with its
window, editor, explorer, output panel, status bar, command palette, highlighter,
and theme manager separated into GUI modules. The compiler implementation remains
in `easylang_studio.py`.

## Preserved application modules
- EasyLang lexer, recursive-descent parser, AST, semantic analysis, three-address-code generator and interpreter
- Modular PySide6 desktop IDE with a VS Code-style activity bar, file explorer, editor tabs, syntax highlighting, open/save/new/close, find, compile and run
- Tokens, AST, symbol table, TAC, output, errors and debugger result views
- VS Code Dark+/Light+ themes, icon toolbar and menus, command palette, keyboard shortcuts, Auto Correction, dockable compiler output
- FIRST/FOLLOW, LL(1) table, predictive parser, left-recursion removal, left factoring, shift/reduce exploration and LR(0)/SLR(1) item-set/table generation
- C++17 compile/run integration using `g++`, isolated build folder and timeouts

## EasyLang syntax
Programs start with `START` and end with `END`. Types are `int` and `string`. Statements: declarations, assignments, `print(...)`, `if`/`else`, and `while`. Blocks use braces; statements end in semicolons; comments start with `//`.

```text
START
int age = 20;
string name = "Ali";
if (age >= 18) {
    print(name);
} else {
    print("Minor");
}
END
```

Arithmetic supports `+ - * /` with conventional precedence and unary minus. Conditions support `== != > < >= <=`. String escapes include `\n`, `\t`, `\"`, and `\\`. Variables use the original project's global symbol-table behavior. Integer division truncates toward zero. Interpreter loop guard: 100,000 steps.

## C++17
Save a `.cpp`, `.cc`, or `.cxx` file, choose C++17, then Compile/Run. `g++` must be on PATH. Set `EASYLANG_GXX` if it is installed at a non-standard path. Build products go into `build/cpp`; execution is limited to 10 seconds.

## Grammar lab
Write one production per line using `->` or `→`, `|` for alternatives, and `ε` for empty productions. Uppercase names are non-terminals. The compact notation `ab` is split into character terminals; space-separated symbols are treated as individual grammar symbols.

## Notes on parity
The Python implementation ports the compiler language semantics and grammar algorithms. Its desktop UI uses PySide6 and provides IDE workflows inspired by VS Code; native window decorations, fonts, menu rendering, and file dialogs still vary by operating system.


## Modern GUI
The default launcher (`run.py`) opens the PySide6 interface:
- Project file explorer on the left
- Syntax-highlighted editor tabs in the center
- Compile, Run, Debug, Stop and language selection in the toolbar
- Dockable Output, Errors, Tokens, AST, Symbol Table, TAC and Debugger panels
- Grammar Workbench dialog for FIRST/FOLLOW, LL(1), predictive parsing,
  left-recursion removal, factoring, shift/reduce and LR(0)/SLR(1)
- Dark and light themes

The compiler and grammar algorithms remain in `easylang_studio.py`; the new GUI
imports and reuses those modules. Install dependencies before launching. A
working C++17 toolchain (`g++`) is still required for C++ compilation.


## Workspace safety update
The modern IDE's File Explorer now starts empty. Use **File → Open Project Folder**
(or the toolbar action) to explicitly choose a workspace; the explorer then roots
its view at that folder instead of automatically exposing the home directory.

## Verified scope and limitations
The bundled compiler is currently a compact educational implementation, not the
full language described in the aspirational development brief. Its verified
EasyLang subset is `int`/`string`, declarations, assignments, `print`, `if`/`else`,
`while`, integer arithmetic, comparisons, and `//` comments. The requested
`float`, `double`, `char`, `bool`, `for`, `do while`, logical and compound
assignment operators, functions, arrays, break/continue, and interactive
instruction-level debugger are **not implemented end-to-end** in this version.
The AST panel is a textual rendering of parser-created AST nodes, not yet the
interactive graphical tree/workspace requested. Auto Correction remains a
limited suggestion mechanism. The C++17 selector is a separate optional path,
not part of the EasyLang compiler pipeline.

## Current validation
Run `python -m unittest discover -s tests -v` from this directory. The existing
seven unit tests pass in the development environment. Python source files pass
bytecode compilation. A live GUI launch was not verified in the development
environment because PySide6 is not installed there; install `requirements.txt`
before launching the desktop interface.


## Visual Compiler Workspace (updated)

Open **View → Visual Compiler Workspace** or press **F7**. The workspace is
integrated into the existing compiler-output dock and adds seven views fed by
the same compile worker result:

1. **Compilation Pipeline** — live stage updates and final success/failure/
   skipped states for source capture, lexing, parsing, AST creation, semantic
   analysis, symbol-table creation, TAC generation, and execution.
2. **AST** — the existing parser-generated tree and graph; selecting a tree or
   graph node navigates to its source line.
3. **Control Flow Graph** — a CFG built from the parser AST for sequential
   statements, `if`/`else`, and `while`, including true/false branches and loop
   back edges. It does not claim support for language constructs absent from
   this compiler.
4. **Token Explorer** — the existing lexer token list with search and source
   navigation.
5. **Symbol Table** — semantic initialization status is distinct from runtime
   values; runtime values are shown only after execution. Search and declaration
   source navigation are available.
6. **Intermediate Code** — the existing CodeGenerator output, with an aligned
   source-line map, search, and copy action. TAC text generation order and text
   are preserved.
7. **Visual Debugger** — uses the existing interpreter pre-statement hook for
   genuine statement-level forward stepping, continue, stop, runtime values,
   and source highlighting. Start, Pause, Step Forward, Resume, and Stop controls
   are available. Backward stepping is not offered because safe interpreter-state
   restoration is not implemented.

The CFG builder and source-map metadata are kept in the visualization/compiler
support path. The pipeline reports a stage as successful only after the
corresponding existing compiler operation returns successfully. For compile-only
runs, execution is marked skipped rather than successful. The C++17 path is
marked not applicable to the EasyLang pipeline.

**Environment note:** install the already-declared dependency with
`python -m pip install -r requirements.txt`. The source package was syntax
checked and compiler/CFG tests were run in the audit environment, but a live
Qt GUI test could not be performed there because PySide6 was unavailable.

## Live web demo (submission deployment)

A separate browser companion is included in `web_demo/`. It reuses the real
EasyLang compiler core from `easylang_studio.py`; the desktop app is not replaced
or altered by the web demo. The browser demo supports source editing, compile/
analysis, bounded execution, output, tokens, AST text, symbol table, TAC, CFG
nodes/edges, and preview-first safe-fix suggestions.

### Run locally

From the project root:

```bash
python -m pip install -r web_demo/requirements.txt
streamlit run web_demo/app.py
```

### Deploy to Streamlit Community Cloud

1. Push the repository to GitHub (public is simplest for a student submission).
2. Open https://share.streamlit.io/ and sign in with GitHub.
3. Create an app and choose the repository, branch, and main file path
   `web_demo/app.py`.
4. Set the requirements path to `web_demo/requirements.txt` if the deployment
   interface asks for it (otherwise its auto-detection may use the root file).
5. Deploy. Streamlit provides the public `*.streamlit.app` URL.
6. Open the URL in a private/incognito window and verify the sample programs,
   run, compile, diagnostics, and Safe Fix flow before submitting.

The live deployment requires an account and a GitHub repository under your
control; this project package includes the deployment-ready source and settings,
not a URL created on your behalf.

### C++17 Visualization
The C++ mode now populates Tokens, AST, Control Flow Graph, Symbol Table, and Intermediate Code views. Clang is used for an actual JSON AST and LLVM IR when available. If Clang is unavailable, the AST and source-line CFG fall back to explicitly labeled approximate source analysis; the source-line CFG does not claim complete branch/loop semantics. The GCC/g++ compiler remains the build/run tool.

### Modulus in EasyLang
Both `%` and `mod` are supported as integer modulus operators. Safe Fix recognizes common `modulus`/`modulas` misspellings and suggests `mod`.

### Graph and Tree Viewing
AST, CFG, and pipeline graph displays include zoom-in, zoom-out, fit-to-view, mouse-wheel zoom, and drag-to-pan controls.
Modulus follows integer remainder behavior with truncation toward zero for negative operands (e.g. `-17 % 5` evaluates to `-2`).
Modulus follows integer remainder behavior with truncation toward zero for negative operands (e.g. `-17 % 5` evaluates to `-2`).
