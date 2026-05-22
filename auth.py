"""
Garmin Connect authentication with session persistence.

First run will prompt for MFA if enabled on the account.
Subsequent runs reuse the saved session from .garth/.

Credentials via env vars:
  GARMIN_EMAIL
  GARMIN_PASSWORD
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv()

TOKENSTORE = Path(__file__).parent / ".garth"


def get_client() -> Garmin:
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    if TOKENSTORE.exists():
        try:
            client = Garmin()
            client.login(str(TOKENSTORE))
            return client
        except Exception:
            pass  # token expired or invalid — fall through to fresh auth

    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: "))
    client.login()
    TOKENSTORE.mkdir(exist_ok=True)
    client.garth.dump(str(TOKENSTORE))
    print(f"Session saved to {TOKENSTORE}")
    return client


if __name__ == "__main__":
    client = get_client()
    profile = client.get_full_name()
    print(f"Authenticated as: {profile}")
