# NEXVARY Voice 0.5.3

- Fix Windows error 448 during managed Python optional minor-version link creation.
- Isolate uv persistent state alongside the existing LocalAppData Python store.
- Detect and functionally probe already extracted Python 3.11 x64, bypass minor-version aliases and reuse healthy downloads.
- Build private venv using the validated explicit interpreter and copied files; preserve existing runtime and models.
- Recover only the identified optional-link failure, never cancellation, failed downloads or unverified extraction.
- Add simulated regression tests and Windows CI with real extracted Python, venv, packages and functional inference after a simulated 448; healthy retry runs no installation commands.
- No Windows protection, firewall, system Python or permissions changes.

The CI policy error is injected after a real download; physical Windows 10 cloud/reparse-point drivers remain untested.
