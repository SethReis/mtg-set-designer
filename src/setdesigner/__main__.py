"""Entry point: `python -m setdesigner` (add --browser to use a browser tab)."""
from setdesigner.ui.app import main

if __name__ in {"__main__", "__mp_main__"}:
    main()
