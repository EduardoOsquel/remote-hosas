import os
import shutil
import subprocess
from unittest.mock import Mock

import pytest

from restore_point import RestorePointError, create_restore_point, restore_script


@pytest.mark.parametrize("code,expected", [(50, "24 hours"), (51, "System Protection"),
                                         (52, "did not confirm"), (53, "declined"), (1, "failed")])
def test_restore_errors_are_explicit_and_never_report_success(code, expected):
    messages = []
    with pytest.raises(RestorePointError, match=expected):
        create_restore_point(messages.append, Mock(return_value=code))
    assert not any("created and verified" in message for message in messages)


def test_success_reports_verified_point():
    messages = []
    create_restore_point(messages.append, Mock(return_value=0))
    assert "created and verified" in messages[-1]


def test_restore_scripts_parse_without_executing_system_changes():
    if not shutil.which("powershell.exe"):
        pytest.skip("Requires Windows PowerShell")
    run = Mock(return_value=0)
    create_restore_point(lambda message: None, run)
    for script in (restore_script("Test ' quoted description"), run.call_args.args[0]):
        parser = ("$t = $null; $e = $null; "
                  "[void][System.Management.Automation.Language.Parser]::ParseInput("
                  "$env:RESTORE_SCRIPT_TEST, [ref]$t, [ref]$e); "
                  "if ($e.Count) { Write-Output $e; exit 1 }; exit 0")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", parser],
                                env={**os.environ, "RESTORE_SCRIPT_TEST": script},
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
