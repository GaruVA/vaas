"""VAAS — Arduino COM-port auto-discovery utility.

Usage
-----
    python scripts/find_arduino.py
    python scripts/find_arduino.py --dry-run
    python scripts/find_arduino.py --quiet

Exit codes
----------
    0   Arduino found (and .env updated unless --dry-run)
    1   No Arduino found on any COM port
    2   More than one candidate found — prints all matches, picks the first one,
        still exits 0 so the launch continues (first match is usually correct)

How it works
------------
pyserial's `serial.tools.list_ports.comports()` returns a list of
`ListPortInfo` objects with `.device`, `.description`, and `.hwid` fields.
We match against a list of well-known VID/PID strings and description
keywords that cover every common Arduino USB-serial chip:

    Chip       Description keyword   VID example
    ---------  --------------------  -----------
    ATmega16U2 "Arduino"             VID:2341 (official Arduino LLC)
    CH340/341  "CH340"               VID:1A86 (common clone boards)
    CP2102/04  "CP210x"              VID:10C4 (SparkFun, NodeMCU, etc.)
    FT232RL    "FTDI"                VID:0403
    PL2303     "PL2303" / "Prolific" VID:067B

The match is case-insensitive and checks both `.description` and `.hwid`
so it fires whether Windows has loaded the vendor INF or not.

The .env update is done with a simple regex line-replacement so comments
and all other values in the file are preserved exactly.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_ARDUINO_KEYWORDS = [
    "arduino",
    "ch340",
    "ch341",
    "cp210",
    "ftdi",
    "ft232",
    "pl2303",
    "prolific",
    "1a86",
    "2341",
    "10c4",
    "0403",
    "067b",
]

_ENV_KEY = "VAAS_ARDUINO_PORT"

def _is_arduino(port_info) -> bool:
    """Return True if *port_info* looks like an Arduino serial adapter."""
    haystack = (
        (port_info.description or "") + " " + (port_info.hwid or "")
    ).lower()
    return any(kw in haystack for kw in _ARDUINO_KEYWORDS)

def scan_ports() -> list:
    """Return list of ListPortInfo that match Arduino heuristics."""
    try:
        from serial.tools import list_ports
    except ImportError:
        print("ERROR: pyserial is not installed.  Run: pip install pyserial", file=sys.stderr)
        sys.exit(1)

    return [p for p in list_ports.comports() if _is_arduino(p)]

def _update_env(env_path: Path, port: str, quiet: bool) -> None:
    """Write *port* into the VAAS_ARDUINO_PORT line of *env_path*.

    If the key is already present its value is replaced in-place so all
    surrounding comments and whitespace are preserved.  If the key is not
    present it is appended at the end of the file.
    """
    if not env_path.exists():
        if not quiet:
            print(f"  .env not found at {env_path} — skipping update.")
        return

    text = env_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^(" + re.escape(_ENV_KEY) + r"\s*=\s*)(.*)$",
        re.MULTILINE,
    )

    if pattern.search(text):
        new_text = pattern.sub(r"\g<1>" + port, text)
    else:

        separator = "\n" if text.endswith("\n") else "\n\n"
        new_text = text + separator + f"{_ENV_KEY}={port}\n"

    env_path.write_text(new_text, encoding="utf-8")
    if not quiet:
        print(f"  .env updated: {_ENV_KEY}={port}")

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan COM ports for an Arduino and update .env automatically."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the detected port but do NOT write to .env",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress all output except errors (useful from .bat scripts)",
    )
    args = parser.parse_args()

    quiet = args.quiet
    env_path = _ROOT / ".env"

    if not quiet:
        print("Scanning COM ports for Arduino ...")

    candidates = scan_ports()

    if not candidates:
        print(
            "  WARNING: No Arduino found on any COM port.\n"
            "  Is the USB cable connected?  Check Device Manager → Ports (COM & LPT).\n"
            "  VAAS_ARDUINO_PORT in .env was NOT changed.",
            file=sys.stderr,
        )
        return 1

    if len(candidates) > 1 and not quiet:
        print(f"  Multiple Arduino-like devices found — using the first:")
        for p in candidates:
            marker = "  ► " if p is candidates[0] else "    "
            print(f"{marker}{p.device}  [{p.description}]  hwid={p.hwid}")

    chosen = candidates[0]
    port = chosen.device

    if not quiet:
        print(f"  Detected: {port}  [{chosen.description}]  hwid={chosen.hwid}")

    if args.dry_run:
        print(f"  Dry-run: would set {_ENV_KEY}={port} in .env")
        return 0

    _update_env(env_path, port, quiet)
    return 0

if __name__ == "__main__":
    sys.exit(main())
