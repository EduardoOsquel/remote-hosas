"""English application messages, with original tool output kept for diagnostics.

External programs follow the OS language. Do not pretend to translate their
output: report the outcome in English and preserve the original separately.
"""

from collections import deque
from datetime import datetime


DIAGNOSTICS = deque(maxlen=100)


def record_result(label, command, returncode, stdout="", stderr="") -> str:
    DIAGNOSTICS.append(
        f"[{datetime.now().isoformat(timespec='seconds')}] {label}\n"
        f"Command: {command!r}\nExit code: {returncode}\n"
        f"Standard output:\n{stdout}\nStandard error:\n{stderr}\n"
    )
    if returncode == 0:
        return f"[OK] {label} completed."
    return (f"[ERROR] {label} failed (exit code: {returncode}; "
            f"0x{returncode & 0xffffffff:08X}). Export diagnostics in Management for details.")


def record_exception(label, command, error) -> str:
    DIAGNOSTICS.append(f"{label}\nCommand: {command!r}\n{type(error).__name__}: {error}\n")
    if isinstance(error, FileNotFoundError):
        return f"[ERROR] {command[0]} was not found. Check its installation and PATH."
    return f"[ERROR] {label} could not run. Export diagnostics in Management for details."
