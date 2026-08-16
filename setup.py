#!/usr/bin/env python3
"""
Garmin Sync setup — run once after cloning.

  python setup.py

Installs dependencies, authenticates with Garmin Connect,
runs an initial backfill, and fetches your physiology profile.
Safe to re-run; skips steps already done.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def ok(msg):   print(f"  ✓ {msg}")
def info(msg): print(f"  · {msg}")
def warn(msg): print(f"  ⚠ {msg}")
def step(n, total, title): print(f"\n[{n}/{total}] {title}")
def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default


def run(cmd, cwd=None, capture=True):
    result = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    if result.returncode != 0:
        lines = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "command failed")
    return result.stdout.strip()


def python() -> str:
    return str(HERE / ".venv" / "bin" / "python")


# ── steps ─────────────────────────────────────────────────────────────────────

def install_deps():
    venv = HERE / ".venv"
    if not venv.exists():
        info("Creating .venv...")
        run([sys.executable, "-m", "venv", str(venv)])
    info("Installing requirements...")
    run([python(), "-m", "pip", "install", "-q", "-r", str(HERE / "requirements.txt")])
    ok("dependencies ready")


def garmin_auth():
    garth = HERE / ".garth" / "garmin_tokens.json"
    if garth.exists():
        ok("session already cached (.garth/) — skipping auth")
        return

    env_file = HERE / ".env"
    has_env_vars = os.environ.get("GARMIN_EMAIL") and os.environ.get("GARMIN_PASSWORD")

    if not env_file.exists() and not has_env_vars:
        print()
        email    = ask("Garmin email")
        password = ask("Garmin password")
        env_file.write_text(f"GARMIN_EMAIL={email}\nGARMIN_PASSWORD={password}\n")
        ok(".env written")
    elif env_file.exists():
        ok(".env found")
    else:
        ok("credentials found in environment")

    info("Authenticating (may take ~10s)...")
    result = subprocess.run([python(), "auth.py"], cwd=HERE)
    if result.returncode != 0:
        warn("Auth failed — try: .venv/bin/python auth_interactive.py")
        if ask("Continue anyway?", "y").lower() != "y":
            sys.exit(1)
    else:
        ok("authenticated")


def initial_sync():
    db = HERE / "garmin.duckdb"
    if db.exists():
        ok(f"garmin.duckdb exists ({db.stat().st_size // 1024} KB) — skipping backfill")
        return

    days = ask("Days to backfill", "30")
    try:
        days = int(days)
    except ValueError:
        days = 30

    info(f"Syncing {days} days...")
    subprocess.run([python(), "sync.py", "--backfill", str(days)], cwd=HERE)
    ok("backfill done")


def fetch_physiology():
    output = HERE / "data" / "physiology.json"
    if output.exists():
        ok("physiology.json exists — skipping")
        return
    info("Fetching physiology from Garmin API...")
    try:
        subprocess.run([python(), "fetch_physiology.py"], cwd=HERE, check=True)
    except subprocess.CalledProcessError as e:
        warn(f"Physiology fetch failed: {e} (non-fatal, can re-run later)")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("\nGarmin Sync — Setup")
    print("─" * 36)

    step(1, 4, "Dependencies")
    install_deps()

    step(2, 4, "Garmin authentication")
    garmin_auth()

    step(3, 4, "Initial sync")
    initial_sync()

    step(4, 4, "Physiology profile")
    fetch_physiology()

    print("\n" + "─" * 36)
    print("Done.\n")
    print("  Database:   ", HERE / "garmin.duckdb")
    print("  Physiology: ", HERE / "data" / "physiology.json")
    print()
    print("  Next: set up Personalkin for notifications and Claude integration.")
    print(f"  Export this path for Personalkin's setup:\n")
    print(f"    export GARMIN_SYNC={HERE}")
    print()


if __name__ == "__main__":
    main()
