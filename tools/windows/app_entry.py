"""PyInstaller executable entry point: no shell or Python console required."""
import sys
from pathlib import Path
import traceback
from voice_engine.desktop_app import main

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        try:
            result=main()
        except Exception:
            destination=Path("build")
            destination.mkdir(exist_ok=True)
            (destination/"frozen-smoke-error.txt").write_text(traceback.format_exc(),encoding="utf-8")
            result=1
        raise SystemExit(result)
    raise SystemExit(main())
