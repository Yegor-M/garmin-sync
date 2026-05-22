"""
Garmin Connect authentication with session persistence.

Subsequent runs reuse the saved session from .garth/ automatically.

Credentials via env vars:
  GARMIN_EMAIL
  GARMIN_PASSWORD
"""

import os
import signal
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from garminconnect import Garmin, GarminConnectConnectionError

load_dotenv()

TOKENSTORE = Path(__file__).parent / ".garth"
LOGIN_TIMEOUT = 45  # seconds before giving up


def _check_connectivity() -> None:
    """Fail fast if Garmin SSO is unreachable or rate-limiting before we even try."""
    print("Checking connectivity to Garmin...")
    try:
        r = requests.head("https://sso.garmin.com", timeout=5)
        if r.status_code == 429:
            print("ERROR: Garmin SSO is returning 429 — IP is rate-limited.")
            print("Wait 30-60 min or switch VPN server, then retry.")
            sys.exit(1)
        print(f"  sso.garmin.com reachable (HTTP {r.status_code})")
    except requests.ConnectionError:
        print("ERROR: Cannot reach sso.garmin.com — check network/VPN.")
        sys.exit(1)
    except requests.Timeout:
        print("ERROR: sso.garmin.com timed out — check network/VPN.")
        sys.exit(1)


def _timeout_handler(signum, frame):
    raise TimeoutError(f"Login timed out after {LOGIN_TIMEOUT}s")


def get_client() -> Garmin:
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    if TOKENSTORE.exists():
        try:
            client = Garmin()
            client.login(str(TOKENSTORE))
            return client
        except Exception:
            print("Saved session expired, re-authenticating...")

    _check_connectivity()

    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: "))

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(LOGIN_TIMEOUT)
    try:
        client.login()
        signal.alarm(0)
    except TimeoutError:
        print(f"\nERROR: Login timed out after {LOGIN_TIMEOUT}s.")
        print("Garmin may be slow to respond. Try again or switch VPN server.")
        sys.exit(1)
    except GarminConnectConnectionError as e:
        signal.alarm(0)
        msg = str(e)
        if "429" in msg:
            print("\nERROR: Rate limited (429). Wait 30-60 min or switch VPN server.")
        elif "CAPTCHA" in msg:
            print("\nERROR: Garmin is requiring CAPTCHA.")
            print("Log in via browser at https://connect.garmin.com, then wait 30 min before retrying.")
        else:
            print(f"\nERROR: Login failed — {e}")
        sys.exit(1)

    TOKENSTORE.mkdir(exist_ok=True)
    client.garth.dump(str(TOKENSTORE))
    print(f"Session saved to {TOKENSTORE}")
    return client


if __name__ == "__main__":
    client = get_client()
    print(f"Authenticated as: {client.get_full_name()}")
