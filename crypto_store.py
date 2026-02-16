import json
import os
import subprocess
from typing import Any, Dict


DB_MAGIC = b"GPG1\n"  # our own tiny header before JSON to sanity-check decrypt output


class CryptoStoreError(Exception):
    pass


def _run_gpg(input_bytes: bytes, args: list[str]) -> bytes:
    """
    Run gpg with given args, feed input_bytes on stdin, return stdout bytes.
    Raises CryptoStoreError with stderr on failure.
    """
    try:
        p = subprocess.run(
            args,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as e:
        raise CryptoStoreError(
            "gpg not found. Install it (mac: brew install gnupg; linux: install gnupg)."
        ) from e

    if p.returncode != 0:
        # include stderr (decoded safely) for debugging
        err = p.stderr.decode("utf-8", errors="replace").strip()
        raise CryptoStoreError(f"gpg failed: {err}")

    return p.stdout


def encrypt_json(password: str, obj: Dict[str, Any]) -> bytes:
    """
    Produces a GPG symmetrically-encrypted blob (OpenPGP format).
    The blob contains: DB_MAGIC + compact JSON bytes.
    """
    plaintext_json = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    plaintext = DB_MAGIC + plaintext_json

    # Passphrase is provided via stdin. We must enable loopback pinentry.
    # Settings chosen to be explicit and reasonably future-accessible.
    #
    # Notes:
    # - --s2k-mode 3 => iterated+salted
    # - --s2k-digest-algo SHA256
    # - --s2k-count controls work factor (higher = slower brute force; also slower unlock)
    #   This is encoded into the OpenPGP packet so it is self-describing.
    gpg_args = [
        "gpg",
        "--batch",
        "--yes",
        "--pinentry-mode",
        "loopback",
        "--passphrase-fd",
        "0",
        "--symmetric",
        "--cipher-algo",
        "AES256",
        "--digest-algo",
        "SHA256",
        "--s2k-mode",
        "3",
        "--s2k-digest-algo",
        "SHA256",
        "--s2k-count",
        "65011712",
        "--compress-algo",
        "none",
        "--output",
        "-",  # write to stdout
        "--no-tty",
    ]

    # stdin = passphrase + newline + data to encrypt is NOT supported directly.
    # So we pass passphrase via fd 0 and data via an extra pipe is needed.
    # Easiest cross-platform approach: use --passphrase-fd 0 AND --decrypt/--encrypt with input on stdin
    # is conflicting. Instead: passphrase on fd 0 and plaintext via a temp file.
    #
    # To keep it simplest and robust: write plaintext to temp file, feed passphrase on stdin.

    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(plaintext)
        tf.flush()
        tmp_path = tf.name

    try:
        # Correct invocation: gpg --symmetric [file]
        gpg_args_with_file = gpg_args + [tmp_path]

        out = _run_gpg((password + "\n").encode("utf-8"), gpg_args_with_file)
        return out
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def decrypt_json(password: str, blob: bytes) -> Dict[str, Any]:
    """
    Decrypts a GPG symmetric blob produced by encrypt_json().
    """
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(blob)
        tf.flush()
        tmp_path = tf.name

    try:
        gpg_args = [
            "gpg",
            "--batch",
            "--yes",
            "--pinentry-mode",
            "loopback",
            "--passphrase-fd",
            "0",
            "--decrypt",
            "--output",
            "-",
            "--no-tty",
            tmp_path,
        ]

        plaintext = _run_gpg((password + "\n").encode("utf-8"), gpg_args)

    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if not plaintext.startswith(DB_MAGIC):
        # This also catches "wrong password but somehow got bytes" (rare) and wrong file type.
        raise CryptoStoreError("Decryption succeeded but content is not recognized (wrong password or corrupt file).")

    plaintext_json = plaintext[len(DB_MAGIC):]
    try:
        return json.loads(plaintext_json.decode("utf-8"))
    except Exception as e:
        raise CryptoStoreError("Decrypted content is not valid JSON (file corrupt?).") from e


def load_db_file(path: str, password: str, default_obj: Dict[str, Any]) -> Dict[str, Any]:
    if not os.path.exists(path):
        return default_obj

    with open(path, "rb") as f:
        blob = f.read()

    return decrypt_json(password, blob)


def save_db_file(path: str, password: str, obj: Dict[str, Any]) -> None:
    blob = encrypt_json(password, obj)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)