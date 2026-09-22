"""Exercise the real Windows GUI interpreter without compiling an EXE."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows GUI handles")
ROOT = Path(__file__).resolve().parents[1]


def test_windowed_installer_helper_preserves_progress():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    result = subprocess.run([str(pythonw), "-B", str(ROOT / "launcher.py"),
        "--installer-helper", "invalid-test-action"], capture_output=True,
        text=True, encoding="utf-8", timeout=20, cwd=ROOT, creationflags=subprocess.DETACHED_PROCESS)
    assert result.returncode == 1
    assert json.loads(result.stdout)["message"] == "[ERROR] Unknown installation action."


def test_windowed_streams_do_not_allocate_a_console():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    code = ("import ctypes, sys; from windowed_io import prepare_output; "
            "sys.stdout = None; sys.stderr = None; prepare_output(helper=True); "
            "assert not ctypes.windll.kernel32.GetConsoleWindow(); "
            "print('progress', flush=True); print('diagnostics', file=sys.stderr, flush=True)")
    result = subprocess.run([str(pythonw), "-B", "-c", code], capture_output=True,
        text=True, encoding="utf-8", timeout=20, cwd=ROOT, creationflags=subprocess.DETACHED_PROCESS)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "progress"
    assert result.stderr.strip() == "diagnostics"
