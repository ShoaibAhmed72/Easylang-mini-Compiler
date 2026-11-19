# EasyLang Studio Web Demo

This is a companion browser demo, not a replacement for the PySide6 desktop IDE.
It imports the actual EasyLang compiler/interpreter and Safe Fix engine from the
parent project.

## Local launch

From the project root:

```bash
python -m pip install -r web_demo/requirements.txt
streamlit run web_demo/app.py
```

## Streamlit Community Cloud deployment

1. Push this project to a GitHub repository.
2. Log into Streamlit Community Cloud at https://share.streamlit.io/ with GitHub.
3. Create an app, select repository/branch, and set the app file to `web_demo/app.py`.
4. Configure dependency file as `web_demo/requirements.txt` if prompted.
5. Deploy, then test the assigned public URL from a private/incognito browser.

The app provides editing, compile/analyze, bounded execution, diagnostics with
hints, preview-first safe fixes, output, tokens, AST, symbol table, TAC, and CFG
node/edge views. The interpreter is the project's bounded educational interpreter;
this is not an arbitrary Python/shell execution service.
