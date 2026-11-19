
## Neon IDE GUI styling refresh
- Updated Dark+ palette to a navy/purple neon style matching the supplied mockup.
- Refined toolbar, tabs, menus, docks, editors, controls, scrollbars, and status bar styling.
- Added New/Open/Save, Visual Compiler Workspace, and Auto Correction shortcuts as toolbar actions without changing their underlying action handlers.
- Added semantic toolbar styling for Run, Debug, Stop, Visual Compiler, and Safe Fix.
- Updated Light+ to a coordinated lavender/clean-light palette.
- No compiler, lexer, parser, semantic, correction, or debugger logic changed in this GUI styling pass.
\n## C++ editor snapshot and Safe Fix reliability (2026-11-19)\n- C++ builds compile the current editor contents, including unsaved changes, rather than the saved disk file.\n- Previous executable is deleted before build, so failed compilation cannot run stale output.\n- Safe Fix merges typo and semicolon edits on a single line, preserves quoted text/comments, adds headers after typo corrections, qualifies standard streams when appropriate, and inserts main return in the correct location.\n- Auto Correction now has Apply Fixes and Apply & Recompile (compile-only) actions.\n- Nonzero C++ runtime exit is reported as an error with captured output.\n
## Targeted fixes (C++ visualization, graph viewport, modulus)
- Added a dedicated C++17 visualization analysis path: source tokens, Clang JSON AST when available, source-level symbol extraction, source-line CFG (explicitly approximate), and LLVM IR when Clang supports it.
- C++ visualization is connected to the existing Tokens, AST, CFG, Symbol Table, and Intermediate Code panels. The EasyLang analysis pipeline remains separate.
- AST/CFG/pipeline graph views now provide Zoom +, Zoom -, Fit to View, wheel zoom, drag pan, and automatic fitting when graphs are generated.
- EasyLang now recognizes `%` and `mod` as modulus operators; parser precedence, semantic checks, constant folding, interpreter execution, and code generation support it.
- Safe Fix corrects the common `modulas`/`modulus` spelling to `mod` in expression lines.
- Added regression tests for modulus and C++ visualization helpers.
- Modulus follows truncation-toward-zero integer remainder behavior for negative operands.
- Modulus follows truncation-toward-zero integer remainder behavior for negative operands.
