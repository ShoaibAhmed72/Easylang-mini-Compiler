"""Browser companion for EasyLang Studio using the project's actual compiler core."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from easylang_studio import Lexer, Parser, SemanticAnalyzer, Interpreter, CodeGenerator, AutoCorrector, CompilerError, CompilerErrors, ast_text

st.set_page_config(page_title="EasyLang Studio Web", page_icon="🟣", layout="wide")
st.markdown("""
<style>
.stApp { background: linear-gradient(135deg,#0b1020,#111a2c 55%,#20123b); color:#e9ecff; }
[data-testid="stHeader"] {background:transparent;}
[data-testid="stSidebar"] {background:#111827; border-right:1px solid #35405e;}
.stButton>button {border-radius:12px;border:1px solid #7651d6;background:linear-gradient(135deg,#49309a,#772fd1);color:white;font-weight:700;}
.stButton>button:hover {border-color:#b78cff;color:white;box-shadow:0 0 14px #7546c880;}
[data-testid="stTextArea"] textarea {background:#0b1220!important;color:#dce8ff!important;border:1px solid #39496a!important;border-radius:12px!important;font-family:Consolas,monospace!important;}
[data-testid="stTabs"] button {color:#d9dfff;}
</style>
""", unsafe_allow_html=True)

SAMPLES = {
    "While loop": "START\nint i = 0;\nwhile (i < 5) {\n    print(i);\n    i = i + 1;\n}\nEND\n",
    "Arithmetic": "START\nint total = 6 * 7;\nprint(total);\nEND\n",
    "If / else": 'START\nint age = 20;\nif (age >= 18) {\n    print("Adult");\n} else {\n    print("Minor");\n}\nEND\n',
    "Strings": 'START\nstring name = "EasyLang";\nprint("Hello, ");\nprint(name);\nEND\n',
}

st.markdown("# 🟣 EasyLang Studio — Web Demo")
st.caption("A browser companion to the desktop IDE. This demo reuses the real EasyLang lexer, parser, semantic analyzer, interpreter, TAC generator and Safe Fix engine from the project.")
with st.sidebar:
    st.markdown("### EasyLang Demo")
    sample_name = st.selectbox("Load sample", list(SAMPLES))
    if st.button("Load selected sample", use_container_width=True):
        st.session_state.source_editor = SAMPLES[sample_name]
    st.markdown("---")
    st.markdown("**Supported subset**")
    st.write("`int`, `string`, declarations, assignments, `print`, `if/else`, `while`, arithmetic, comparisons, `//` comments")
    st.info("Execution uses the bounded project interpreter, not arbitrary Python or shell commands.")

if "source_editor" not in st.session_state:
    st.session_state.source_editor = SAMPLES["While loop"]

left, right = st.columns([1.45, 1], gap="large")
with left:
    st.markdown("### Code Editor")
    source = st.text_area("EasyLang source", height=400, label_visibility="collapsed", key="source_editor")
    c1, c2, c3 = st.columns(3)
    run_clicked = c1.button("▶ Run Program", use_container_width=True)
    compile_clicked = c2.button("⚙ Compile / Analyze", use_container_width=True)
    fix_clicked = c3.button("✨ Find Safe Fixes", use_container_width=True)
with right:
    st.markdown("### Safe Fix Suggestions")
    corrector = AutoCorrector(source)
    fixes = corrector.suggestions()
    if not fixes:
        st.success("No mechanical safe fixes detected.")
    else:
        st.caption(f"{len(fixes)} suggestion(s) detected")
        selected_fixes = []
        for index, (line, description, replacement) in enumerate(fixes):
            selected = st.checkbox(f"Line {line}: {description}", value=True, key=f"fix_{index}_{line}_{description}")
            if selected:
                selected_fixes.append(line)
            if replacement not in ("START", "END", "}"):
                st.code(replacement, language="text")
        if st.button("Apply selected safe fixes", use_container_width=True):
            st.session_state.source_editor = corrector.apply(selected_fixes)
            st.success("Selected fixes applied. Review the updated code, then run it.")
            st.rerun()

if run_clicked or compile_clicked or fix_clicked:
    st.session_state.last_action = "run" if run_clicked else "compile" if compile_clicked else "fix"
    st.session_state.last_source = source
    st.session_state.result = None
    st.session_state.diagnostics = []
    try:
        tokens = Lexer(source).scan()
        program = Parser(tokens).parse()
        semantic = SemanticAnalyzer()
        symbols = semantic.analyze(program)
        tac = CodeGenerator().generate(program)
        output = ""
        if run_clicked:
            output = Interpreter(timeout=2.0).run(program)
        st.session_state.result = {
            "tokens": tokens, "program": program, "symbols": symbols,
            "tac": tac, "output": output, "ast": ast_text(program),
            "status": "Run successful" if run_clicked else "Compilation successful",
        }
    except CompilerError as error:
        diagnostics = getattr(error, "errors", [error])
        st.session_state.diagnostics = diagnostics
        st.session_state.safe_error_fixes = AutoCorrector(source).suggestions_for_error(error)
        st.session_state.result = {"status": "Failed", "error": str(error)}

result = st.session_state.get("result")
if result:
    if result.get("error"):
        st.error(result["error"])
        for diagnostic in st.session_state.get("diagnostics", []):
            st.markdown(f"**{diagnostic.category} — Line {diagnostic.line}, Column {diagnostic.column}**")
            st.write(diagnostic.message)
            st.caption(f"Hint: {diagnostic.hint}")
        error_fixes = st.session_state.get("safe_error_fixes", [])
        if error_fixes:
            st.markdown("#### Safe fixes related to diagnostics")
            for line, description, replacement in error_fixes:
                st.write(f"- Line {line}: **{description}**")
    else:
        st.success(result["status"])
        tabs = st.tabs(["Output", "Tokens", "AST", "Symbol Table", "Three Address Code", "CFG"])
        with tabs[0]:
            st.code(result["output"] or "(Program produced no output)", language="text")
        with tabs[1]:
            st.dataframe([{"Type": t.type, "Lexeme": t.lexeme, "Line": t.line, "Column": t.column} for t in result["tokens"]], use_container_width=True, hide_index=True)
        with tabs[2]:
            st.code(result["ast"], language="text")
        with tabs[3]:
            st.dataframe([{"Name": name, "Type": info["type"], "Value": info.get("value")} for name, info in result["symbols"].items()], use_container_width=True, hide_index=True)
        with tabs[4]:
            st.code(result["tac"] or "(No TAC generated)", language="text")
        with tabs[5]:
            try:
                from visualizations.cfg_builder import build_cfg
                graph = build_cfg(result["program"])
                st.write("Nodes")
                st.dataframe([{"ID": node.id, "Kind": node.kind, "Label": node.label, "Line": node.line} for node in graph.nodes.values()], use_container_width=True, hide_index=True)
                st.write("Edges")
                st.dataframe([{"From": edge.source, "To": edge.target, "Branch": edge.label} for edge in graph.edges], use_container_width=True, hide_index=True)
            except Exception as exc:
                st.warning(f"CFG visualization unavailable: {exc}")

st.markdown("---")
st.caption("Educational demo: the deployed web version exposes the EasyLang compiler subset and compiler views. The full desktop IDE remains the primary project, including its Qt workspace and desktop-specific tools.")
