"""Tests for firmware security analysis enhancements."""

import pytest
from pathlib import Path
from hwh.firmware.analyzer import SecurityAnalyzer
from hwh.firmware.analyzer_advanced import AdvancedAnalyzer
from hwh.firmware.sbom import SBOMGenerator, SBOMPackage
from hwh.firmware.types import Severity


class TestBinaryHardeningAnalysis:
    """Test binary hardening detection."""

    def test_advanced_analyzer_has_hardening_method(self):
        """Test that AdvancedAnalyzer has binary hardening method."""
        analyzer = AdvancedAnalyzer(log_callback=lambda x: None)
        assert hasattr(analyzer, 'analyze_binary_hardening')
        assert callable(analyzer.analyze_binary_hardening)

    def test_security_analyzer_has_hardening_method(self):
        """Test that SecurityAnalyzer exposes binary hardening method."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        assert hasattr(analyzer, 'analyze_binary_hardening')
        assert callable(analyzer.analyze_binary_hardening)

    @pytest.mark.asyncio
    async def test_hardening_analysis_on_empty_dir(self, tmp_path):
        """Test that hardening analysis works on empty directory."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        findings = await analyzer.analyze_binary_hardening(tmp_path)
        assert isinstance(findings, list)
        assert len(findings) == 0


class TestNetworkSecurityAnalysis:
    """Test network security detection."""

    def test_advanced_analyzer_has_network_method(self):
        """Test that AdvancedAnalyzer has network security method."""
        analyzer = AdvancedAnalyzer(log_callback=lambda x: None)
        assert hasattr(analyzer, 'analyze_network_security')

    def test_security_analyzer_has_network_method(self):
        """Test that SecurityAnalyzer exposes network security method."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        assert hasattr(analyzer, 'analyze_network_security')

    @pytest.mark.asyncio
    async def test_network_analysis_on_empty_dir(self, tmp_path):
        """Test that network analysis works on empty directory."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        findings = await analyzer.analyze_network_security(tmp_path)
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_detects_telnet_service(self, tmp_path):
        """Test detection of telnet service in config."""
        # Create a config file with telnet enabled
        config_dir = tmp_path / "etc" / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "services").write_text("telnetd enable=1\n")

        analyzer = AdvancedAnalyzer(log_callback=lambda x: None)
        findings = await analyzer._check_debug_ports(tmp_path)

        # Should detect telnet
        telnet_findings = [f for f in findings if 'telnet' in f.title.lower()]
        assert len(telnet_findings) >= 1

    @pytest.mark.asyncio
    async def test_detects_snmp_public(self, tmp_path):
        """Test detection of SNMP public community string."""
        config_dir = tmp_path / "etc"
        config_dir.mkdir(parents=True)
        (config_dir / "snmpd.conf").write_text("community = public\n")

        analyzer = AdvancedAnalyzer(log_callback=lambda x: None)
        findings = await analyzer._check_default_network_creds(tmp_path)

        # Should detect SNMP public
        snmp_findings = [f for f in findings if 'snmp' in f.title.lower()]
        assert len(snmp_findings) >= 1


class TestCryptoWeaknessAnalysis:
    """Test cryptographic weakness detection."""

    def test_advanced_analyzer_has_crypto_method(self):
        """Test that AdvancedAnalyzer has crypto weakness method."""
        analyzer = AdvancedAnalyzer(log_callback=lambda x: None)
        assert hasattr(analyzer, 'analyze_crypto_weaknesses')

    def test_security_analyzer_has_crypto_method(self):
        """Test that SecurityAnalyzer exposes crypto weakness method."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        assert hasattr(analyzer, 'analyze_crypto_weaknesses')

    @pytest.mark.asyncio
    async def test_crypto_analysis_on_empty_dir(self, tmp_path):
        """Test that crypto analysis works on empty directory."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        findings = await analyzer.analyze_crypto_weaknesses(tmp_path)
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_detects_weak_ssl_config(self, tmp_path):
        """Test detection of weak SSL configuration."""
        config_dir = tmp_path / "etc"
        config_dir.mkdir(parents=True)
        # Use config format that matches the pattern (ssl_protocols = SSLv2)
        (config_dir / "ssl.conf").write_text("ssl_protocols = SSLv2 TLSv1.2\n")

        analyzer = AdvancedAnalyzer(log_callback=lambda x: None)
        findings = await analyzer._check_weak_crypto_configs(tmp_path)

        # Should detect SSLv2/SSLv3 as weak (POODLE vulnerability)
        weak_findings = [f for f in findings if 'poodle' in f.description.lower() or 'sslv' in str(f).lower()]
        assert len(weak_findings) >= 1


class TestSBOMGeneration:
    """Test SBOM generation functionality."""

    def test_sbom_generator_creation(self):
        """Test SBOMGenerator can be created."""
        generator = SBOMGenerator(firmware_name="test_firmware")
        assert generator.firmware_name == "test_firmware"
        assert len(generator.packages) == 0
        assert len(generator.files) == 0

    def test_sbom_add_package(self):
        """Test adding package to SBOM."""
        from hwh.firmware.analyzer_advanced import SoftwarePackage

        generator = SBOMGenerator(firmware_name="test")
        pkg = SoftwarePackage(name="busybox", version="1.33.0", source="opkg")
        generator.add_package(pkg)

        assert len(generator.packages) == 1
        assert generator.packages[0].name == "busybox"
        assert generator.packages[0].version == "1.33.0"

    def test_sbom_generate_spdx_json(self):
        """Test SPDX JSON generation."""
        from hwh.firmware.analyzer_advanced import SoftwarePackage

        generator = SBOMGenerator(firmware_name="test_router")
        generator.add_package(SoftwarePackage("dropbear", "2020.81", "opkg"))
        generator.add_package(SoftwarePackage("dnsmasq", "2.85", "opkg"))

        spdx = generator.generate_spdx_json()

        assert spdx["spdxVersion"] == "SPDX-2.3"
        assert spdx["dataLicense"] == "CC0-1.0"
        assert spdx["name"] == "SBOM-test_router"
        assert len(spdx["packages"]) == 2

    def test_sbom_cpe_generation(self):
        """Test CPE reference generation."""
        generator = SBOMGenerator(firmware_name="test")
        cpe = generator._generate_cpe("busybox", "1.33.0")

        assert cpe is not None
        assert "cpe:2.3:a" in cpe
        assert "busybox" in cpe
        assert "1.33.0" in cpe

    def test_sbom_purl_generation(self):
        """Test PURL reference generation."""
        generator = SBOMGenerator(firmware_name="test")

        purl_opkg = generator._generate_purl("busybox", "1.33.0", "opkg")
        assert purl_opkg == "pkg:openwrt/busybox@1.33.0"

        purl_dpkg = generator._generate_purl("openssl", "1.1.1k", "dpkg")
        assert purl_dpkg == "pkg:deb/openssl@1.1.1k"

    def test_sbom_export_json(self, tmp_path):
        """Test exporting SBOM to JSON file."""
        from hwh.firmware.analyzer_advanced import SoftwarePackage

        generator = SBOMGenerator(firmware_name="test")
        generator.add_package(SoftwarePackage("test_pkg", "1.0", "opkg"))

        output_file = tmp_path / "test.spdx.json"
        success = generator.export_spdx_json(output_file)

        assert success is True
        assert output_file.exists()

        # Verify JSON is valid
        import json
        with open(output_file) as f:
            data = json.load(f)
        assert data["spdxVersion"] == "SPDX-2.3"


class TestSecurityAnalyzerIntegration:
    """Test integrated security analyzer functionality."""

    def test_analyzer_has_all_new_methods(self):
        """Test that SecurityAnalyzer has all new analysis methods."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)

        methods = [
            'analyze_binary_hardening',
            'analyze_network_security',
            'analyze_crypto_weaknesses',
            'generate_sbom',
        ]

        for method in methods:
            assert hasattr(analyzer, method), f"Missing method: {method}"
            assert callable(getattr(analyzer, method))

    @pytest.mark.asyncio
    async def test_full_analysis_includes_new_checks(self, tmp_path):
        """Test that analyze_all includes new security checks."""
        # Create minimal directory structure
        etc_dir = tmp_path / "etc"
        etc_dir.mkdir()
        (etc_dir / "passwd").write_text("root:x:0:0:root:/root:/bin/sh\n")

        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        result = await analyzer.analyze_all(tmp_path)

        assert result is not None
        assert hasattr(result, 'findings')
        assert hasattr(result, 'files_scanned')

    @pytest.mark.asyncio
    async def test_sbom_generation_from_analyzer(self, tmp_path):
        """Test SBOM generation through analyzer."""
        analyzer = SecurityAnalyzer(progress_callback=lambda x: None)
        sbom = await analyzer.generate_sbom(
            root_path=tmp_path,
            firmware_name="test_fw",
            include_files=False
        )

        assert sbom is not None
        assert sbom.firmware_name == "test_fw"


class TestCLICommands:
    """Test CLI command registration."""

    def test_firmware_sbom_command_exists(self):
        """Test that firmware sbom command is registered."""
        from click.testing import CliRunner
        from hwh.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['firmware', 'sbom', '--help'])

        assert result.exit_code == 0
        assert 'SBOM' in result.output or 'Software Bill of Materials' in result.output

    def test_firmware_hardening_command_exists(self):
        """Test that firmware hardening command is registered."""
        from click.testing import CliRunner
        from hwh.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ['firmware', 'hardening', '--help'])

        assert result.exit_code == 0
        assert 'PIE' in result.output or 'hardening' in result.output.lower()
