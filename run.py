"""Launch the modern PySide6 EasyLang Studio interface."""
try:
    from easylang_qt import main
except ImportError as exc:
    raise SystemExit(
        "PySide6 is required for the modern GUI. Install it with: python -m pip install PySide6"
    ) from exc

if __name__ == "__main__":
    main()
