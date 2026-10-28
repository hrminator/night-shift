"""Generate a VAPID key pair for Web Push and print it ONCE.

The operator stores the two printed values as the VAPID_PUBLIC_KEY and
VAPID_PRIVATE_KEY environment variables (Fly secrets on the live site).
Nothing is written to the repo.

Run: uv run python scripts/make_vapid.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")


def main() -> None:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from py_vapid import Vapid
    from py_vapid.utils import b64urlencode

    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    private_raw = private_key.private_numbers().private_value.to_bytes(
        32, "big")
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public_text = b64urlencode(public_raw)
    private_text = b64urlencode(private_raw)
    check = Vapid.from_string(private_text).public_key.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    assert b64urlencode(check) == public_text, "VAPID round-trip failed"
    print("Store these as environment variables (shown ONCE, never again):")
    print(f"VAPID_PUBLIC_KEY={public_text}")
    print(f"VAPID_PRIVATE_KEY={private_text}")


if __name__ == "__main__":
    main()
