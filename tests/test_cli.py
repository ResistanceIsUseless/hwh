"""Tests for hwh CLI."""

import pytest
from click.testing import CliRunner
from hwh.cli import cli
from hwh import __version__


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_cli_help(self, runner):
        """Test that CLI help works."""
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Hardware Hacking Toolkit' in result.output

    def test_cli_version(self, runner):
        """Test that version flag works."""
        result = runner.invoke(cli, ['--version'])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_cli_verbose_flag(self, runner):
        """Test that verbose flag is accepted."""
        result = runner.invoke(cli, ['-v', 'devices'])
        # Should not fail due to the flag
        assert result.exit_code == 0


class TestDeviceCommands:
    """Test device detection commands."""

    def test_devices_command(self, runner):
        """Test devices command runs."""
        result = runner.invoke(cli, ['devices'])
        # Should run without error (may find no devices)
        assert result.exit_code == 0

    def test_detect_command(self, runner):
        """Test detect command (alias)."""
        result = runner.invoke(cli, ['detect'])
        assert result.exit_code == 0

    def test_devices_json_output(self, runner):
        """Test devices command with JSON output."""
        result = runner.invoke(cli, ['devices', '--json'])
        assert result.exit_code == 0
        # Output should be valid JSON (starts with [ or empty)
        output = result.output.strip()
        assert output.startswith('[') or output == ''

    def test_devices_show_all(self, runner):
        """Test devices command with --all flag."""
        result = runner.invoke(cli, ['devices', '--all'])
        assert result.exit_code == 0


class TestSPICommands:
    """Test SPI commands."""

    def test_spi_help(self, runner):
        """Test SPI subcommand help."""
        result = runner.invoke(cli, ['spi', '--help'])
        assert result.exit_code == 0
        assert 'SPI flash operations' in result.output

    def test_spi_dump_help(self, runner):
        """Test SPI dump help."""
        result = runner.invoke(cli, ['spi', 'dump', '--help'])
        assert result.exit_code == 0
        assert '--output' in result.output

    def test_spi_id_help(self, runner):
        """Test SPI id help."""
        result = runner.invoke(cli, ['spi', 'id', '--help'])
        assert result.exit_code == 0


class TestI2CCommands:
    """Test I2C commands."""

    def test_i2c_help(self, runner):
        """Test I2C subcommand help."""
        result = runner.invoke(cli, ['i2c', '--help'])
        assert result.exit_code == 0
        assert 'I2C operations' in result.output

    def test_i2c_scan_help(self, runner):
        """Test I2C scan help."""
        result = runner.invoke(cli, ['i2c', 'scan', '--help'])
        assert result.exit_code == 0


class TestGlitchCommands:
    """Test glitch commands."""

    def test_glitch_help(self, runner):
        """Test glitch subcommand help."""
        result = runner.invoke(cli, ['glitch', '--help'])
        assert result.exit_code == 0
        assert 'Voltage glitching' in result.output

    def test_glitch_single_help(self, runner):
        """Test glitch single help."""
        result = runner.invoke(cli, ['glitch', 'single', '--help'])
        assert result.exit_code == 0
        assert '--width' in result.output
        assert '--offset' in result.output

    def test_glitch_sweep_help(self, runner):
        """Test glitch sweep help."""
        result = runner.invoke(cli, ['glitch', 'sweep', '--help'])
        assert result.exit_code == 0
        assert '--width-min' in result.output
        assert '--width-max' in result.output


class TestDebugCommands:
    """Test debug commands."""

    def test_debug_help(self, runner):
        """Test debug subcommand help."""
        result = runner.invoke(cli, ['debug', '--help'])
        assert result.exit_code == 0
        assert 'Debug/SWD operations' in result.output

    def test_debug_dump_help(self, runner):
        """Test debug dump help."""
        result = runner.invoke(cli, ['debug', 'dump', '--help'])
        assert result.exit_code == 0
        assert '--address' in result.output

    def test_debug_regs_help(self, runner):
        """Test debug regs help."""
        result = runner.invoke(cli, ['debug', 'regs', '--help'])
        assert result.exit_code == 0


class TestTUICommand:
    """Test TUI command."""

    def test_tui_help(self, runner):
        """Test TUI command help."""
        result = runner.invoke(cli, ['tui', '--help'])
        assert result.exit_code == 0
        assert 'TUI' in result.output or 'Terminal' in result.output


class TestShellCommand:
    """Test shell command."""

    def test_shell_help(self, runner):
        """Test shell command help."""
        result = runner.invoke(cli, ['shell', '--help'])
        assert result.exit_code == 0
        assert 'shell' in result.output.lower()
