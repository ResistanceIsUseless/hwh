"""Tests for hwh CLI."""

from click.testing import CliRunner
from hwh.cli import cli


def test_cli_help():
    """Test that CLI help works."""
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'Hardware Hacking Toolkit' in result.output


def test_cli_version():
    """Test that version flag works."""
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert '0.1.0' in result.output


def test_devices_command():
    """Test devices command runs."""
    runner = CliRunner()
    result = runner.invoke(cli, ['devices'])
    # Should run without error (may find no devices)
    assert result.exit_code == 0
