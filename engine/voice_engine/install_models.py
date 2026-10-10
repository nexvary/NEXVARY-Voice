"""Explicit opt-in Argos model installer; uses official Argos package index."""
from __future__ import annotations

import argparse


def install(source: str, target: str) -> None:
    try:
        import argostranslate.package as packages
    except ImportError as exc:
        raise SystemExit("Run: pip install '.[offline]'") from exc
    packages.update_package_index()
    available = packages.get_available_packages()
    matches = [p for p in available if p.from_code == source and p.to_code == target]
    if not matches:
        raise SystemExit(f"No direct Argos package advertised for {source} -> {target}. Try installing a pivot via English.")
    selected = matches[0]
    path = selected.download()
    packages.install_from_path(path)
    print(f"Installed {source} -> {target} ({selected.package_version})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--accept-download", action="store_true")
    args = parser.parse_args()
    if not args.accept_download:
        parser.error("Provide --accept-download to explicitly allow model download")
    install(args.source, args.target)


if __name__ == "__main__":
    main()
