import sys
sys.path.insert(0, ".")

import os
import tempfile
from unittest.mock import patch


def test_cli_stats():
    from cli import cmd_stats
    class Args:
        pass
    with patch("builtins.print") as mock_print:
        cmd_stats(Args())
        assert mock_print.called


def test_cli_backup_create():
    from cli import cmd_backup_create
    class Args:
        pass
    with patch("builtins.print") as mock_print:
        cmd_backup_create(Args())
        assert mock_print.called


def test_cli_backup_list():
    from cli import cmd_backup_list
    class Args:
        pass
    with patch("builtins.print") as mock_print:
        cmd_backup_list(Args())
        assert mock_print.called


def test_cli_employees_list():
    from cli import cmd_employees_list
    class Args:
        limit = 5
    with patch("builtins.print") as mock_print:
        cmd_employees_list(Args())
        assert mock_print.called


def test_cli_violations_list():
    from cli import cmd_violations_list
    class Args:
        limit = 5
    with patch("builtins.print") as mock_print:
        cmd_violations_list(Args())
        assert mock_print.called


def test_cli_violations_export_csv():
    from cli import cmd_violations_export
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        fname = f.name
    try:
        class Args:
            format = "csv"
            output = fname
        cmd_violations_export(Args())
        assert os.path.getsize(fname) > 0
    finally:
        os.unlink(fname)
