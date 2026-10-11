"""PyInstaller executable entry point: no shell or Python console required."""
from voice_engine.desktop_app import main

if __name__ == "__main__":
    raise SystemExit(main())
