#!/usr/bin/env python3
"""Rotate the Checker signing key. This is the ONLY tool that may create a
private key or write data/checker/public_key.hex, and only with --confirm-rotate.
Run: uv run python tools/rotate_key.py --confirm-rotate
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import checker
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rotate the Checker Ed25519 signing key.")
    parser.add_argument("--confirm-rotate", action="store_true",
                        help="required: generate a new key and rewrite the pinned public key")
    args = parser.parse_args(argv)
    if not args.confirm_rotate:
        parser.error("--confirm-rotate is required; refusing to create a key or write the pin")
    key = Ed25519PrivateKey.generate()
    checker.KEYS.mkdir(parents=True, exist_ok=True)
    (checker.KEYS / "private_key.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    (checker.KEYS / "public_key.hex").write_text(pub + "\n")
    print("rotated: new private key written and public_key.hex updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
