"""
First-time authentication via garth directly.

Use this instead of auth.py when the scripted login hits CAPTCHA or MFA issues.
It does a single clean attempt — no strategy cycling, no retries.

Usage:
  .venv/bin/python auth_interactive.py

After success, .garth/ is saved and auth.py / sync.py / explore.py
will reuse the session without re-authenticating.
"""

import os
from pathlib import Path

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="garth")

from dotenv import load_dotenv
import garth.http

load_dotenv()

TOKENSTORE = Path(__file__).parent / ".garth"


def main():
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    client = garth.http.Client()
    print("Attempting login via garth...")
    client.login(email, password, prompt_mfa=lambda: input("MFA code: "))

    TOKENSTORE.mkdir(exist_ok=True)
    client.dump(str(TOKENSTORE))
    print(f"Session saved to {TOKENSTORE}")
    print(f"Logged in as: {client.username}")


if __name__ == "__main__":
    main()
