"""Hash a password the same way `app.auth.hash_password` does.

Use this to generate a bcrypt hash to paste into a user's `password_hash`
field in ArangoDB when resetting a forgotten password.

Usage:
    python scripts/hash_password.py "the new password"
    python scripts/hash_password.py          # prompts without echoing input
"""

import getpass
import sys

import bcrypt


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("password must be at most 72 bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def main() -> None:
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("Password to hash: ")

    print(hash_password(password))


if __name__ == "__main__":
    main()
