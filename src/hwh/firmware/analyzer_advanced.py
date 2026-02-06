"""
Advanced Firmware Analysis

Extended analysis methods for service detection, software versions,
custom binaries, scheduled tasks, and nuclei integration.
"""

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple

from .types import Finding, Severity


@dataclass
class ServiceInfo:
    """Information about a detected service"""
    name: str
    type: str  # systemd, init.d, xinetd, etc.
    enabled: bool
    config_path: Optional[Path] = None
    binary_path: Optional[Path] = None
    ports: List[str] = None

    def __post_init__(self):
        if self.ports is None:
            self.ports = []


@dataclass
class SoftwarePackage:
    """Information about installed software"""
    name: str
    version: str
    source: str  # opkg, dpkg, rpm, etc.
    cves: List[str] = None

    def __post_init__(self):
        if self.cves is None:
            self.cves = []


@dataclass
class CustomBinary:
    """Information about custom/interesting binaries"""
    path: Path
    size: int
    stripped: bool
    arch: str
    interesting_strings: List[str] = None
    interesting_functions: List[str] = None

    def __post_init__(self):
        if self.interesting_strings is None:
            self.interesting_strings = []
        if self.interesting_functions is None:
            self.interesting_functions = []


class AdvancedAnalyzer:
    """Advanced firmware analysis methods"""

    def __init__(self, log_callback):
        self._log = log_callback
        self.services: List[ServiceInfo] = []
        self.packages: List[SoftwarePackage] = []
        self.custom_binaries: List[CustomBinary] = []

    async def analyze_services(self, root_path: Path) -> List[Finding]:
        """Analyze running services and daemons"""
        self._log("[*] Analyzing services and daemons...")
        findings = []

        # Check systemd units
        systemd_paths = [
            root_path / "etc/systemd/system",
            root_path / "lib/systemd/system",
            root_path / "usr/lib/systemd/system",
        ]

        for systemd_dir in systemd_paths:
            if systemd_dir.exists():
                for unit_file in systemd_dir.rglob("*.service"):
                    service_info = await self._parse_systemd_unit(unit_file, root_path)
                    if service_info:
                        self.services.append(service_info)

                        # Check for risky service configurations
                        try:
                            content = unit_file.read_text(errors="ignore")

                            # Check for root execution without hardening
                            if "User=root" in content or "User=" not in content:
                                if "ProtectSystem=" not in content and "PrivateTmp=" not in content:
                                    findings.append(Finding(
                                        severity=Severity.MEDIUM,
                                        category="service",
                                        title=f"Service runs as root without hardening: {service_info.name}",
                                        description="Service runs with elevated privileges but lacks systemd hardening",
                                        file_path=unit_file.relative_to(root_path)
                                    ))

                            # Check for network-facing services
                            if any(port in content.lower() for port in ["listenstream", "listendatagram"]):
                                findings.append(Finding(
                                    severity=Severity.INFO,
                                    category="service",
                                    title=f"Network service detected: {service_info.name}",
                                    description="Service listens on network socket",
                                    file_path=unit_file.relative_to(root_path)
                                ))
                        except Exception:
                            pass

        # Check init.d scripts
        initd_dir = root_path / "etc/init.d"
        if initd_dir.exists():
            for init_script in initd_dir.iterdir():
                if init_script.is_file() and init_script.stat().st_mode & 0o111:
                    service_info = ServiceInfo(
                        name=init_script.name,
                        type="init.d",
                        enabled=True,  # Assume enabled if script exists
                        config_path=init_script
                    )
                    self.services.append(service_info)

                    # Check for common vulnerabilities in init scripts
                    try:
                        content = init_script.read_text(errors="ignore")

                        # Check for use of eval
                        if re.search(r'\beval\b', content):
                            findings.append(Finding(
                                severity=Severity.HIGH,
                                category="service",
                                title=f"Init script uses eval: {init_script.name}",
                                description="Use of eval() can lead to command injection vulnerabilities",
                                file_path=init_script.relative_to(root_path)
                            ))

                        # Check for unquoted variables
                        if re.search(r'\$\w+(?!\})', content):
                            findings.append(Finding(
                                severity=Severity.LOW,
                                category="service",
                                title=f"Init script has unquoted variables: {init_script.name}",
                                description="Unquoted variables can lead to word splitting issues",
                                file_path=init_script.relative_to(root_path)
                            ))
                    except Exception:
                        pass

        # Check xinetd configurations
        xinetd_dir = root_path / "etc/xinetd.d"
        if xinetd_dir.exists():
            for xinetd_conf in xinetd_dir.iterdir():
                if xinetd_conf.is_file():
                    try:
                        content = xinetd_conf.read_text(errors="ignore")
                        service_name = xinetd_conf.name

                        disabled = "disable" in content and "= yes" in content

                        service_info = ServiceInfo(
                            name=service_name,
                            type="xinetd",
                            enabled=not disabled,
                            config_path=xinetd_conf
                        )
                        self.services.append(service_info)

                        # Check for services without access controls
                        if "only_from" not in content and not disabled:
                            findings.append(Finding(
                                severity=Severity.MEDIUM,
                                category="service",
                                title=f"xinetd service lacks access controls: {service_name}",
                                description="Service has no IP-based access restrictions",
                                file_path=xinetd_conf.relative_to(root_path)
                            ))
                    except Exception:
                        pass

        self._log(f"[+] Found {len(self.services)} services")
        return findings

    async def _parse_systemd_unit(self, unit_file: Path, root_path: Path) -> Optional[ServiceInfo]:
        """Parse a systemd unit file"""
        try:
            content = unit_file.read_text(errors="ignore")

            # Extract ExecStart
            exec_start = None
            for line in content.split('\n'):
                if line.startswith('ExecStart='):
                    exec_start = line.split('=', 1)[1].strip()
                    break

            # Check if enabled (WantedBy or RequiredBy section)
            enabled = "WantedBy=" in content or "RequiredBy=" in content

            return ServiceInfo(
                name=unit_file.stem,
                type="systemd",
                enabled=enabled,
                config_path=unit_file,
                binary_path=Path(exec_start.split()[0]) if exec_start else None
            )
        except Exception:
            return None

    async def analyze_software_versions(self, root_path: Path) -> List[Finding]:
        """Detect installed software versions and check for CVEs"""
        self._log("[*] Analyzing installed software packages...")
        findings = []

        # Check opkg status (common in embedded Linux)
        opkg_status = root_path / "usr/lib/opkg/status"
        if opkg_status.exists():
            packages = await self._parse_opkg_status(opkg_status)
            self.packages.extend(packages)
            self._log(f"[+] Found {len(packages)} opkg packages")

        # Check dpkg status (Debian-based)
        dpkg_status = root_path / "var/lib/dpkg/status"
        if dpkg_status.exists():
            packages = await self._parse_dpkg_status(dpkg_status)
            self.packages.extend(packages)
            self._log(f"[+] Found {len(packages)} dpkg packages")

        # Check RPM database (would need rpm tools)
        rpm_db = root_path / "var/lib/rpm"
        if rpm_db.exists():
            self._log("[*] RPM database found (requires rpm tools for full analysis)")

        # Check for known vulnerable versions
        vulnerable_patterns = {
            r'busybox.*1\.2[0-9]': 'BusyBox 1.2x has multiple CVEs including command injection',
            r'dropbear.*201[0-7]': 'Dropbear SSH versions before 2018 have known vulnerabilities',
            r'dnsmasq.*2\.[0-6]': 'dnsmasq 2.6x and earlier have DNS spoofing vulnerabilities',
            r'openssl.*1\.0\.1[a-f]': 'OpenSSL 1.0.1a-f vulnerable to Heartbleed (CVE-2014-0160)',
            r'bash.*4\.[0-2]': 'Bash 4.0-4.2 vulnerable to Shellshock (CVE-2014-6271)',
        }

        for pkg in self.packages:
            pkg_str = f"{pkg.name} {pkg.version}".lower()
            for pattern, description in vulnerable_patterns.items():
                if re.search(pattern, pkg_str):
                    findings.append(Finding(
                        severity=Severity.CRITICAL,
                        category="vulnerable_software",
                        title=f"Vulnerable package: {pkg.name} {pkg.version}",
                        description=description,
                        matched_text=f"{pkg.name} {pkg.version}"
                    ))

        return findings

    async def _parse_opkg_status(self, status_file: Path) -> List[SoftwarePackage]:
        """Parse opkg status file"""
        packages = []
        try:
            content = status_file.read_text(errors="ignore")
            current_pkg = {}

            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    if current_pkg.get('name') and current_pkg.get('version'):
                        packages.append(SoftwarePackage(
                            name=current_pkg['name'],
                            version=current_pkg['version'],
                            source='opkg'
                        ))
                    current_pkg = {}
                elif ': ' in line:
                    key, value = line.split(': ', 1)
                    if key == 'Package':
                        current_pkg['name'] = value
                    elif key == 'Version':
                        current_pkg['version'] = value
        except Exception:
            pass

        return packages

    async def _parse_dpkg_status(self, status_file: Path) -> List[SoftwarePackage]:
        """Parse dpkg status file"""
        packages = []
        try:
            content = status_file.read_text(errors="ignore")
            current_pkg = {}

            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    if current_pkg.get('name') and current_pkg.get('version'):
                        packages.append(SoftwarePackage(
                            name=current_pkg['name'],
                            version=current_pkg['version'],
                            source='dpkg'
                        ))
                    current_pkg = {}
                elif ': ' in line:
                    key, value = line.split(': ', 1)
                    if key == 'Package':
                        current_pkg['name'] = value
                    elif key == 'Version':
                        current_pkg['version'] = value
        except Exception:
            pass

        return packages

    async def find_custom_binaries(self, root_path: Path) -> List[Finding]:
        """Identify custom/vendor binaries for further analysis in Ghidra"""
        self._log("[*] Identifying custom binaries for reverse engineering...")
        findings = []

        # Common system binary paths to exclude
        system_paths = {
            '/bin', '/sbin', '/usr/bin', '/usr/sbin', '/lib', '/usr/lib'
        }

        # Look for ELF binaries
        for binary_path in root_path.rglob("*"):
            if not binary_path.is_file():
                continue

            # Skip if in system path
            rel_path = binary_path.relative_to(root_path)
            if any(str(rel_path).startswith(sp.lstrip('/')) for sp in system_paths):
                # But still check if it's a custom name
                known_bins = {'busybox', 'sh', 'bash', 'ls', 'cat', 'grep', 'sed', 'awk'}
                if binary_path.name.lower() in known_bins:
                    continue

            # Check for ELF magic
            try:
                with open(binary_path, 'rb') as f:
                    magic = f.read(4)
                if magic != b'\x7fELF':
                    continue
            except Exception:
                continue

            # This is potentially a custom binary
            size = binary_path.stat().st_size

            # Use file command to get more info
            file_info = await self._run_file_command(binary_path)
            stripped = 'stripped' in file_info.lower()

            # Extract architecture
            arch = "unknown"
            if 'ARM' in file_info:
                arch = "ARM"
            elif 'MIPS' in file_info:
                arch = "MIPS"
            elif 'x86-64' in file_info:
                arch = "x86_64"
            elif '80386' in file_info or 'Intel' in file_info:
                arch = "x86"

            # Extract interesting strings
            interesting_strings = await self._extract_interesting_strings(binary_path)

            binary_info = CustomBinary(
                path=rel_path,
                size=size,
                stripped=stripped,
                arch=arch,
                interesting_strings=interesting_strings
            )
            self.custom_binaries.append(binary_info)

            # Report custom binaries as findings
            findings.append(Finding(
                severity=Severity.INFO,
                category="custom_binary",
                title=f"Custom binary for analysis: {binary_path.name}",
                description=f"{arch} binary, {size:,} bytes, {'stripped' if stripped else 'not stripped'}",
                file_path=rel_path,
                matched_text=f"Interesting strings: {', '.join(interesting_strings[:3])}"
            ))

        self._log(f"[+] Found {len(self.custom_binaries)} custom binaries for Ghidra analysis")
        return findings

    async def _run_file_command(self, path: Path) -> str:
        """Run file command on binary"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["file", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            )
            return result.stdout
        except Exception:
            return ""

    async def _extract_interesting_strings(self, binary_path: Path) -> List[str]:
        """Extract interesting strings from binary"""
        interesting = []
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["strings", "-n", "6", str(binary_path)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            )

            # Look for interesting patterns
            patterns = [
                r'https?://\S+',  # URLs
                r'/dev/\w+',  # Device paths
                r'password|secret|key',  # Credentials
                r'0x[0-9a-fA-F]{8,}',  # Addresses
                r'/tmp/\S+',  # Temp files
            ]

            for line in result.stdout.split('\n')[:100]:  # First 100 strings
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        interesting.append(line.strip())
                        if len(interesting) >= 10:
                            return interesting[:10]
        except Exception:
            pass

        return interesting[:10]

    async def analyze_scheduled_tasks(self, root_path: Path) -> List[Finding]:
        """Analyze cron jobs and startup scripts"""
        self._log("[*] Analyzing scheduled tasks and startup scripts...")
        findings = []

        # Check cron directories
        cron_dirs = [
            root_path / "etc/cron.d",
            root_path / "etc/cron.daily",
            root_path / "etc/cron.hourly",
            root_path / "etc/cron.weekly",
            root_path / "etc/cron.monthly",
            root_path / "var/spool/cron",
            root_path / "var/spool/cron/crontabs",
        ]

        for cron_dir in cron_dirs:
            if cron_dir.exists():
                for cron_file in cron_dir.rglob("*"):
                    if cron_file.is_file():
                        try:
                            content = cron_file.read_text(errors="ignore")
                            rel_path = cron_file.relative_to(root_path)

                            # Check for suspicious cron jobs
                            if re.search(r'curl.*\|\s*sh', content) or re.search(r'wget.*\|\s*sh', content):
                                findings.append(Finding(
                                    severity=Severity.CRITICAL,
                                    category="scheduled_task",
                                    title=f"Suspicious cron job pipes network content to shell: {cron_file.name}",
                                    description="Cron job downloads and executes code from network",
                                    file_path=rel_path
                                ))

                            # Check for world-writable script execution
                            for line in content.split('\n'):
                                if line.strip() and not line.strip().startswith('#'):
                                    # Extract command
                                    parts = line.split()
                                    if len(parts) > 5:
                                        cmd_path = parts[5]
                                        if cmd_path.startswith('/'):
                                            full_path = root_path / cmd_path.lstrip('/')
                                            if full_path.exists():
                                                mode = full_path.stat().st_mode
                                                if mode & 0o002:  # World-writable
                                                    findings.append(Finding(
                                                        severity=Severity.HIGH,
                                                        category="scheduled_task",
                                                        title=f"Cron executes world-writable script: {cmd_path}",
                                                        description="Scheduled task runs script that can be modified by any user",
                                                        file_path=rel_path
                                                    ))
                        except Exception:
                            pass

        # Check system crontabs
        crontab_files = [
            root_path / "etc/crontab",
            root_path / "etc/cron.deny",
            root_path / "etc/cron.allow",
        ]

        for crontab in crontab_files:
            if crontab.exists():
                findings.append(Finding(
                    severity=Severity.INFO,
                    category="scheduled_task",
                    title=f"Crontab configuration found: {crontab.name}",
                    description="Review scheduled tasks",
                    file_path=crontab.relative_to(root_path)
                ))

        # Check rc.local and startup scripts
        startup_scripts = [
            root_path / "etc/rc.local",
            root_path / "etc/rc.d/rc.local",
            root_path / "etc/init.d/rc.local",
        ]

        for startup in startup_scripts:
            if startup.exists():
                try:
                    content = startup.read_text(errors="ignore")
                    rel_path = startup.relative_to(root_path)

                    findings.append(Finding(
                        severity=Severity.INFO,
                        category="startup",
                        title=f"Startup script found: {startup.name}",
                        description="Executes at boot time",
                        file_path=rel_path
                    ))

                    # Check for suspicious startup commands
                    if re.search(r'curl.*\|\s*sh', content) or re.search(r'wget.*\|\s*sh', content):
                        findings.append(Finding(
                            severity=Severity.CRITICAL,
                            category="startup",
                            title=f"Startup script downloads and executes code: {startup.name}",
                            description="Boot-time script fetches and runs code from network",
                            file_path=rel_path
                        ))
                except Exception:
                    pass

        return findings

    async def run_nuclei_scan(self, root_path: Path) -> List[Finding]:
        """Run nuclei scanner on extracted filesystem"""
        self._log("[*] Running nuclei filesystem scan...")
        findings = []

        # Check if nuclei is installed
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["which", "nuclei"],
                    capture_output=True,
                    text=True
                )
            )
            if not result.stdout.strip():
                self._log("[!] nuclei not installed, skipping")
                self._log("[*] Install: go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest")
                return findings
        except Exception:
            self._log("[!] nuclei not found, skipping")
            return findings

        # Run nuclei with file-based templates
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "nuclei",
                        "-t", "file",  # File-based templates
                        "-target", str(root_path),
                        "-json",
                        "-silent",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
            )

            # Parse JSON output
            for line in result.stdout.split('\n'):
                if line.strip():
                    try:
                        data = json.loads(line)

                        # Map nuclei severity to our severity
                        severity_map = {
                            'critical': Severity.CRITICAL,
                            'high': Severity.HIGH,
                            'medium': Severity.MEDIUM,
                            'low': Severity.LOW,
                            'info': Severity.INFO,
                        }
                        severity = severity_map.get(data.get('info', {}).get('severity', 'info').lower(), Severity.INFO)

                        findings.append(Finding(
                            severity=severity,
                            category="nuclei",
                            title=f"Nuclei: {data.get('info', {}).get('name', 'Unknown')}",
                            description=data.get('info', {}).get('description', ''),
                            file_path=Path(data.get('matched-at', '').replace(str(root_path), '').lstrip('/')),
                            matched_text=data.get('matched-line', '')
                        ))
                    except json.JSONDecodeError:
                        pass

            self._log(f"[+] Nuclei found {len(findings)} findings")
        except subprocess.TimeoutExpired:
            self._log("[!] Nuclei scan timed out")
        except Exception as e:
            self._log(f"[!] Nuclei scan failed: {e}")

        return findings

    async def analyze_privilege_escalation(self, root_path: Path) -> List[Finding]:
        """LinPEAS-style privilege escalation analysis"""
        self._log("[*] Analyzing privilege escalation vectors (linpeas-style)...")
        findings = []

        # Check SUID/SGID binaries
        findings.extend(await self._check_suid_sgid_binaries(root_path))

        # Check world-writable files and directories
        findings.extend(await self._check_writable_files(root_path))

        # Check sudo configuration
        findings.extend(await self._check_sudo_config(root_path))

        # Check for interesting capabilities
        findings.extend(await self._check_capabilities(root_path))

        # Check environment variables in configs
        findings.extend(await self._check_environment_variables(root_path))

        # Check for weak file permissions
        findings.extend(await self._check_weak_permissions(root_path))

        self._log(f"[+] Found {len(findings)} privilege escalation vectors")
        return findings

    async def _check_suid_sgid_binaries(self, root_path: Path) -> List[Finding]:
        """Check for SUID/SGID binaries (linpeas-style)"""
        findings = []

        # Common interesting SUID binaries
        interesting_suids = {
            'nmap', 'vim', 'vi', 'find', 'bash', 'sh', 'more', 'less', 'nano',
            'cp', 'mv', 'awk', 'perl', 'python', 'ruby', 'lua', 'php', 'socat',
            'wget', 'curl', 'nc', 'netcat', 'tcpdump', 'wireshark', 'tshark'
        }

        # Check bin directories for SUID/SGID
        bin_dirs = [
            root_path / "bin",
            root_path / "sbin",
            root_path / "usr/bin",
            root_path / "usr/sbin",
            root_path / "usr/local/bin",
            root_path / "usr/local/sbin",
        ]

        for bin_dir in bin_dirs:
            if not bin_dir.exists():
                continue

            for binary in bin_dir.rglob("*"):
                if not binary.is_file():
                    continue

                try:
                    stat = binary.stat()
                    mode = stat.st_mode

                    # Check for SUID (04000) or SGID (02000)
                    if mode & 0o4000:  # SUID
                        severity = Severity.HIGH if binary.name in interesting_suids else Severity.MEDIUM
                        findings.append(Finding(
                            severity=severity,
                            category="privilege_escalation",
                            title=f"SUID binary: {binary.name}",
                            description=f"Binary has SUID bit set, can execute as owner",
                            file_path=binary.relative_to(root_path),
                            matched_text=f"Permissions: {oct(mode)[-4:]}"
                        ))
                    elif mode & 0o2000:  # SGID
                        findings.append(Finding(
                            severity=Severity.LOW,
                            category="privilege_escalation",
                            title=f"SGID binary: {binary.name}",
                            description=f"Binary has SGID bit set, can execute as group",
                            file_path=binary.relative_to(root_path),
                            matched_text=f"Permissions: {oct(mode)[-4:]}"
                        ))
                except (OSError, PermissionError):
                    pass

        return findings

    async def _check_writable_files(self, root_path: Path) -> List[Finding]:
        """Check for world-writable files and directories"""
        findings = []

        # Sensitive paths that shouldn't be writable
        sensitive_paths = [
            "etc/passwd",
            "etc/shadow",
            "etc/sudoers",
            "root/.ssh",
            "etc/cron.d",
            "etc/crontab",
        ]

        for sensitive in sensitive_paths:
            path = root_path / sensitive
            if not path.exists():
                continue

            try:
                stat = path.stat()
                mode = stat.st_mode

                # Check if world-writable (0o002)
                if mode & 0o002:
                    findings.append(Finding(
                        severity=Severity.CRITICAL,
                        category="privilege_escalation",
                        title=f"World-writable sensitive file: {sensitive}",
                        description="Sensitive file is writable by any user",
                        file_path=Path(sensitive),
                        matched_text=f"Permissions: {oct(mode)[-4:]}"
                    ))
                # Check if group-writable for sensitive files
                elif mode & 0o020 and sensitive in ['etc/passwd', 'etc/shadow', 'etc/sudoers']:
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        category="privilege_escalation",
                        title=f"Group-writable sensitive file: {sensitive}",
                        description="Sensitive file is writable by group members",
                        file_path=Path(sensitive),
                        matched_text=f"Permissions: {oct(mode)[-4:]}"
                    ))
            except (OSError, PermissionError):
                pass

        return findings

    async def _check_sudo_config(self, root_path: Path) -> List[Finding]:
        """Check sudo configuration for vulnerabilities"""
        findings = []

        sudoers_file = root_path / "etc/sudoers"
        if sudoers_file.exists():
            try:
                content = sudoers_file.read_text(errors="ignore")

                # Check for NOPASSWD entries
                if "NOPASSWD:" in content:
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        category="privilege_escalation",
                        title="Sudo NOPASSWD configuration found",
                        description="Users can execute sudo commands without password",
                        file_path=Path("etc/sudoers"),
                        matched_text="NOPASSWD entries found"
                    ))

                # Check for wildcard sudo rules
                if re.search(r'ALL\s*=.*\*', content):
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        category="privilege_escalation",
                        title="Wildcard in sudo configuration",
                        description="Sudo rules contain wildcards that may be exploitable",
                        file_path=Path("etc/sudoers")
                    ))

                # Check for dangerous sudo commands
                dangerous_cmds = ['vim', 'vi', 'nano', 'less', 'more', 'find', 'awk', 'perl', 'python', 'ruby']
                for cmd in dangerous_cmds:
                    if re.search(rf'\b{cmd}\b', content, re.IGNORECASE):
                        findings.append(Finding(
                            severity=Severity.MEDIUM,
                            category="privilege_escalation",
                            title=f"Dangerous sudo command allowed: {cmd}",
                            description=f"{cmd} in sudoers can be used to escape to shell",
                            file_path=Path("etc/sudoers"),
                            matched_text=cmd
                        ))
            except (OSError, PermissionError):
                pass

        # Check sudoers.d directory
        sudoers_d = root_path / "etc/sudoers.d"
        if sudoers_d.exists():
            for sudo_file in sudoers_d.iterdir():
                if sudo_file.is_file():
                    try:
                        content = sudo_file.read_text(errors="ignore")
                        if "NOPASSWD:" in content:
                            findings.append(Finding(
                                severity=Severity.HIGH,
                                category="privilege_escalation",
                                title=f"Sudo NOPASSWD in {sudo_file.name}",
                                description="Passwordless sudo configuration",
                                file_path=sudo_file.relative_to(root_path)
                            ))
                    except (OSError, PermissionError):
                        pass

        return findings

    async def _check_capabilities(self, root_path: Path) -> List[Finding]:
        """Check for interesting Linux capabilities"""
        findings = []

        # Capabilities that can lead to privilege escalation
        dangerous_caps = {
            'cap_setuid': 'Can change UID, potential privilege escalation',
            'cap_setgid': 'Can change GID, potential privilege escalation',
            'cap_sys_admin': 'Can perform system administration operations',
            'cap_sys_ptrace': 'Can trace arbitrary processes',
            'cap_sys_module': 'Can load kernel modules',
            'cap_dac_override': 'Can bypass file permission checks',
            'cap_dac_read_search': 'Can bypass file read permission checks',
        }

        # Note: Actual capability checking requires getcap command
        # For firmware analysis, we document that this should be checked post-boot
        findings.append(Finding(
            severity=Severity.INFO,
            category="privilege_escalation",
            title="Check capabilities on live system",
            description="Run 'getcap -r / 2>/dev/null' on live system to check for dangerous capabilities",
            matched_text="Capabilities: " + ", ".join(dangerous_caps.keys())
        ))

        return findings

    async def _check_environment_variables(self, root_path: Path) -> List[Finding]:
        """Check for dangerous environment variables in configs"""
        findings = []

        # Check common shell rc files
        rc_files = [
            ".bashrc",
            ".profile",
            ".bash_profile",
            ".zshrc",
            "etc/profile",
            "etc/bash.bashrc",
            "etc/environment",
        ]

        for rc_file in rc_files:
            path = root_path / rc_file
            if not path.exists():
                continue

            try:
                content = path.read_text(errors="ignore")

                # Check for LD_PRELOAD
                if "LD_PRELOAD" in content:
                    findings.append(Finding(
                        severity=Severity.MEDIUM,
                        category="privilege_escalation",
                        title=f"LD_PRELOAD in {rc_file}",
                        description="LD_PRELOAD can be used to inject malicious libraries",
                        file_path=Path(rc_file)
                    ))

                # Check for PATH manipulation
                if re.search(r'PATH=["\'.]', content):
                    findings.append(Finding(
                        severity=Severity.LOW,
                        category="privilege_escalation",
                        title=f"Suspicious PATH in {rc_file}",
                        description="PATH includes current directory or unusual paths",
                        file_path=Path(rc_file)
                    ))
            except (OSError, PermissionError):
                pass

        return findings

    async def _check_weak_permissions(self, root_path: Path) -> List[Finding]:
        """Check for weak file permissions on critical files"""
        findings = []

        # SSH keys should not be world-readable
        ssh_dirs = [
            "root/.ssh",
            "home/*/.ssh",
        ]

        for ssh_pattern in ssh_dirs:
            for ssh_dir in root_path.glob(ssh_pattern):
                if not ssh_dir.exists() or not ssh_dir.is_dir():
                    continue

                for key_file in ssh_dir.iterdir():
                    if not key_file.is_file():
                        continue

                    try:
                        stat = key_file.stat()
                        mode = stat.st_mode

                        # Private keys should be 600
                        if key_file.suffix in ['', '.pem'] or 'id_' in key_file.name:
                            if mode & 0o077:  # Any group/other permissions
                                findings.append(Finding(
                                    severity=Severity.HIGH,
                                    category="privilege_escalation",
                                    title=f"Weak permissions on SSH key: {key_file.name}",
                                    description="SSH private key has overly permissive permissions",
                                    file_path=key_file.relative_to(root_path),
                                    matched_text=f"Permissions: {oct(mode)[-4:]}"
                                ))
                    except (OSError, PermissionError):
                        pass

        # Check for world-readable /etc/shadow
        shadow_file = root_path / "etc/shadow"
        if shadow_file.exists():
            try:
                stat = shadow_file.stat()
                mode = stat.st_mode

                if mode & 0o004:  # World-readable
                    findings.append(Finding(
                        severity=Severity.CRITICAL,
                        category="privilege_escalation",
                        title="World-readable /etc/shadow",
                        description="Password hashes are readable by all users",
                        file_path=Path("etc/shadow"),
                        matched_text=f"Permissions: {oct(mode)[-4:]}"
                    ))
            except (OSError, PermissionError):
                pass

        return findings

    # =========================================================================
    # Binary Hardening Analysis
    # =========================================================================

    async def analyze_binary_hardening(self, root_path: Path) -> List[Finding]:
        """
        Check ELF binaries for security hardening features.

        Checks for:
        - PIE (Position Independent Executable)
        - RELRO (Relocation Read-Only)
        - Stack Canaries
        - NX (No-Execute stack)
        - FORTIFY_SOURCE
        """
        self._log("[*] Analyzing binary security hardening...")
        findings = []

        # Find ELF binaries
        elf_binaries = []
        for binary_path in root_path.rglob("*"):
            if not binary_path.is_file():
                continue
            try:
                with open(binary_path, 'rb') as f:
                    magic = f.read(4)
                if magic == b'\x7fELF':
                    elf_binaries.append(binary_path)
            except Exception:
                continue

        self._log(f"[*] Found {len(elf_binaries)} ELF binaries to analyze")

        analyzed = 0
        for binary_path in elf_binaries:
            # Skip very large binaries
            if binary_path.stat().st_size > 50 * 1024 * 1024:  # 50MB
                continue

            hardening = await self._check_binary_hardening(binary_path)
            if hardening:
                rel_path = binary_path.relative_to(root_path)

                # Report missing hardening as findings
                if not hardening.get('pie', True):
                    findings.append(Finding(
                        severity=Severity.MEDIUM,
                        category="binary_hardening",
                        title=f"No PIE: {binary_path.name}",
                        description="Binary is not position-independent, making ASLR less effective",
                        file_path=rel_path,
                        matched_text="PIE: disabled"
                    ))

                if not hardening.get('relro', True):
                    findings.append(Finding(
                        severity=Severity.MEDIUM,
                        category="binary_hardening",
                        title=f"No RELRO: {binary_path.name}",
                        description="Binary lacks RELRO, GOT entries are writable",
                        file_path=rel_path,
                        matched_text="RELRO: none"
                    ))
                elif hardening.get('relro') == 'partial':
                    findings.append(Finding(
                        severity=Severity.LOW,
                        category="binary_hardening",
                        title=f"Partial RELRO: {binary_path.name}",
                        description="Binary has partial RELRO, consider full RELRO",
                        file_path=rel_path,
                        matched_text="RELRO: partial"
                    ))

                if not hardening.get('nx', True):
                    findings.append(Finding(
                        severity=Severity.HIGH,
                        category="binary_hardening",
                        title=f"Executable stack (No NX): {binary_path.name}",
                        description="Stack is executable, allowing shellcode execution",
                        file_path=rel_path,
                        matched_text="NX: disabled"
                    ))

                if not hardening.get('canary', True):
                    findings.append(Finding(
                        severity=Severity.MEDIUM,
                        category="binary_hardening",
                        title=f"No Stack Canary: {binary_path.name}",
                        description="Binary lacks stack canary protection against buffer overflows",
                        file_path=rel_path,
                        matched_text="Stack Canary: disabled"
                    ))

                analyzed += 1
                if analyzed >= 100:  # Limit to first 100 binaries
                    self._log("[*] Analyzed 100 binaries, stopping...")
                    break

        self._log(f"[+] Analyzed {analyzed} binaries for hardening")
        return findings

    async def _check_binary_hardening(self, binary_path: Path) -> Optional[Dict]:
        """Check hardening features of a single ELF binary"""
        try:
            with open(binary_path, 'rb') as f:
                elf_data = f.read(min(f.seek(0, 2), 65536))  # Read up to 64KB
                f.seek(0)

            hardening = {
                'pie': False,
                'relro': 'none',
                'nx': True,  # Assume NX unless we find executable stack
                'canary': False,
                'fortify': False,
            }

            # Parse ELF header
            if len(elf_data) < 52:
                return None

            # Check ELF type (offset 16-17)
            e_type = int.from_bytes(elf_data[16:18], 'little')
            # 2 = ET_EXEC (not PIE), 3 = ET_DYN (PIE or shared lib)
            hardening['pie'] = (e_type == 3)

            # Check for stack canary by looking for __stack_chk_fail
            if b'__stack_chk_fail' in elf_data:
                hardening['canary'] = True

            # Check for FORTIFY_SOURCE by looking for _chk functions
            fortify_funcs = [b'__printf_chk', b'__sprintf_chk', b'__strcpy_chk',
                           b'__memcpy_chk', b'__strcat_chk']
            if any(func in elf_data for func in fortify_funcs):
                hardening['fortify'] = True

            # Use readelf to get more accurate info if available
            detailed = await self._run_readelf(binary_path)
            if detailed:
                hardening.update(detailed)

            return hardening

        except Exception:
            return None

    async def _run_readelf(self, binary_path: Path) -> Optional[Dict]:
        """Use readelf to get detailed hardening info"""
        try:
            # Check for GNU_RELRO
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ['readelf', '-l', str(binary_path)],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            )

            info = {}
            if result.returncode == 0:
                output = result.stdout

                # Check for RELRO
                if 'GNU_RELRO' in output:
                    info['relro'] = 'partial'
                    # Full RELRO also has BIND_NOW
                    if 'BIND_NOW' in output or '(NOW)' in output:
                        info['relro'] = 'full'
                else:
                    info['relro'] = 'none'

                # Check for GNU_STACK
                if 'GNU_STACK' in output:
                    # Look for RWE (read-write-execute)
                    lines = output.split('\n')
                    for line in lines:
                        if 'GNU_STACK' in line:
                            if 'RWE' in line or ' E' in line.split('GNU_STACK')[0]:
                                info['nx'] = False
                            else:
                                info['nx'] = True
                            break

            return info if info else None

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    # =========================================================================
    # Network Security Analysis
    # =========================================================================

    async def analyze_network_security(self, root_path: Path) -> List[Finding]:
        """
        Analyze network configuration for security issues.

        Checks for:
        - HTTP-only web servers (no TLS)
        - Open debug ports (Telnet, FTP)
        - UPnP enabled
        - Weak firewall rules
        - Default network credentials
        """
        self._log("[*] Analyzing network security configuration...")
        findings = []

        # Check for HTTP-only web server configs
        findings.extend(await self._check_http_only_servers(root_path))

        # Check for debug ports in service configs
        findings.extend(await self._check_debug_ports(root_path))

        # Check for UPnP
        findings.extend(await self._check_upnp(root_path))

        # Check for WPA/WiFi credentials
        findings.extend(await self._check_wifi_credentials(root_path))

        # Check for default network credentials
        findings.extend(await self._check_default_network_creds(root_path))

        return findings

    async def _check_http_only_servers(self, root_path: Path) -> List[Finding]:
        """Check for web servers not using TLS"""
        findings = []

        web_configs = [
            ("etc/nginx/nginx.conf", "nginx"),
            ("etc/nginx/sites-enabled/*", "nginx"),
            ("etc/nginx/conf.d/*.conf", "nginx"),
            ("etc/apache2/apache2.conf", "apache"),
            ("etc/apache2/sites-enabled/*", "apache"),
            ("etc/lighttpd/lighttpd.conf", "lighttpd"),
            ("etc/httpd/conf/httpd.conf", "apache"),
            ("etc/uhttpd/*", "uhttpd"),
            ("etc/config/uhttpd", "uhttpd"),
        ]

        for config_pattern, server_type in web_configs:
            for config_file in root_path.glob(config_pattern):
                if not config_file.is_file():
                    continue

                try:
                    content = config_file.read_text(errors="ignore")

                    # Check if listening on port 80 without corresponding 443
                    has_http = re.search(r'listen\s+.*:?80\b', content) or \
                               re.search(r'Listen\s+80\b', content) or \
                               re.search(r"option\s+listen_http.*'0\.0\.0\.0:80'", content)

                    has_https = re.search(r'listen\s+.*:?443\b', content) or \
                                re.search(r'Listen\s+443\b', content) or \
                                re.search(r'ssl\s+(on|enable)', content, re.I) or \
                                re.search(r"option\s+listen_https", content)

                    if has_http and not has_https:
                        findings.append(Finding(
                            severity=Severity.MEDIUM,
                            category="network_security",
                            title=f"HTTP-only web server: {server_type}",
                            description=f"{server_type} configured to listen on HTTP without HTTPS",
                            file_path=config_file.relative_to(root_path),
                            matched_text="Port 80 without TLS"
                        ))

                    # Check for self-signed certificate warnings disabled
                    if re.search(r'ssl_verify\s*(off|false|0)', content, re.I):
                        findings.append(Finding(
                            severity=Severity.HIGH,
                            category="network_security",
                            title="SSL verification disabled",
                            description="SSL certificate verification is disabled",
                            file_path=config_file.relative_to(root_path),
                            matched_text="ssl_verify off"
                        ))

                except Exception:
                    pass

        return findings

    async def _check_debug_ports(self, root_path: Path) -> List[Finding]:
        """Check for dangerous debug ports enabled"""
        findings = []

        # Patterns for debug service detection
        debug_patterns = {
            "telnet": (r'telnetd?\s+(start|enable|=\s*1)', Severity.HIGH,
                      "Telnet service enabled - transmits credentials in cleartext"),
            "ftp": (r'(?:vs)?ftpd?\s+(start|enable|=\s*1)', Severity.HIGH,
                   "FTP service enabled - transmits credentials in cleartext"),
            "tftp": (r'tftpd?\s+(start|enable|=\s*1)', Severity.MEDIUM,
                    "TFTP service enabled - no authentication"),
            "rsh": (r'rsh[d]?\s+(start|enable|=\s*1)', Severity.CRITICAL,
                   "RSH service enabled - extremely insecure"),
            "rlogin": (r'rlogin[d]?\s+(start|enable|=\s*1)', Severity.CRITICAL,
                      "Rlogin service enabled - extremely insecure"),
            "debug_port": (r'debug[_-]?port\s*[=:]\s*\d+', Severity.HIGH,
                          "Debug port configured - potential backdoor"),
        }

        # Search in common config locations
        config_patterns = [
            "etc/inetd.conf",
            "etc/xinetd.d/*",
            "etc/config/*",
            "etc/init.d/*",
            "etc/rc.local",
            "etc/default/*",
        ]

        for pattern in config_patterns:
            for config_file in root_path.glob(pattern):
                if not config_file.is_file():
                    continue

                try:
                    content = config_file.read_text(errors="ignore").lower()

                    for service, (regex, severity, desc) in debug_patterns.items():
                        if re.search(regex, content, re.I):
                            findings.append(Finding(
                                severity=severity,
                                category="network_security",
                                title=f"{service.upper()} service detected",
                                description=desc,
                                file_path=config_file.relative_to(root_path),
                                matched_text=service
                            ))

                except Exception:
                    pass

        return findings

    async def _check_upnp(self, root_path: Path) -> List[Finding]:
        """Check for UPnP enabled"""
        findings = []

        upnp_patterns = [
            "etc/config/upnpd",
            "etc/miniupnpd.conf",
            "etc/upnpd.conf",
        ]

        for pattern in upnp_patterns:
            upnp_file = root_path / pattern
            if upnp_file.exists():
                try:
                    content = upnp_file.read_text(errors="ignore")

                    # Check if enabled
                    if re.search(r'enable\s*[=:]\s*(1|true|yes)', content, re.I):
                        findings.append(Finding(
                            severity=Severity.MEDIUM,
                            category="network_security",
                            title="UPnP service enabled",
                            description="UPnP can be used to open firewall ports from the LAN",
                            file_path=upnp_file.relative_to(root_path),
                            matched_text="UPnP enabled"
                        ))

                except Exception:
                    pass

        return findings

    async def _check_wifi_credentials(self, root_path: Path) -> List[Finding]:
        """Check for hardcoded WiFi credentials"""
        findings = []

        wifi_configs = [
            "etc/wpa_supplicant.conf",
            "etc/wpa_supplicant/*.conf",
            "etc/config/wireless",
            "etc/hostapd.conf",
            "etc/hostapd/*.conf",
        ]

        for pattern in wifi_configs:
            for config_file in root_path.glob(pattern):
                if not config_file.is_file():
                    continue

                try:
                    content = config_file.read_text(errors="ignore")

                    # Check for WPA PSK
                    psk_match = re.search(r'(psk|wpa_passphrase)\s*[=:]\s*["\']?([^"\'\n]+)', content, re.I)
                    if psk_match:
                        # Don't report if it's a hash (64 hex chars)
                        psk = psk_match.group(2)
                        if len(psk) != 64 or not all(c in '0123456789abcdefABCDEF' for c in psk):
                            findings.append(Finding(
                                severity=Severity.HIGH,
                                category="network_security",
                                title="Hardcoded WiFi password",
                                description="WiFi password found in configuration",
                                file_path=config_file.relative_to(root_path),
                                matched_text=f"{psk_match.group(1)}=***"
                            ))

                    # Check for weak encryption
                    if re.search(r'auth_algs\s*[=:]\s*1', content) or \
                       re.search(r'wep_key', content, re.I):
                        findings.append(Finding(
                            severity=Severity.CRITICAL,
                            category="network_security",
                            title="WEP encryption detected",
                            description="WEP is cryptographically broken",
                            file_path=config_file.relative_to(root_path),
                            matched_text="WEP encryption"
                        ))

                except Exception:
                    pass

        return findings

    async def _check_default_network_creds(self, root_path: Path) -> List[Finding]:
        """Check for default network service credentials"""
        findings = []

        # Default credential patterns
        default_creds = [
            (r'community\s*[=:]\s*["\']?public["\']?', "SNMP public community string"),
            (r'community\s*[=:]\s*["\']?private["\']?', "SNMP private community string"),
            (r'password\s*[=:]\s*["\']?(admin|root|password|1234|default)["\']?', "Default password"),
            (r'auth[_-]?pass\s*[=:]\s*["\']?(admin|root|password)["\']?', "Default auth password"),
        ]

        config_files = list(root_path.glob("etc/**/*.conf")) + \
                       list(root_path.glob("etc/config/*"))

        for config_file in config_files:
            if not config_file.is_file():
                continue

            try:
                content = config_file.read_text(errors="ignore")

                for pattern, description in default_creds:
                    if re.search(pattern, content, re.I):
                        findings.append(Finding(
                            severity=Severity.HIGH,
                            category="network_security",
                            title=f"Default credentials: {description}",
                            description=description,
                            file_path=config_file.relative_to(root_path),
                            matched_text=re.search(pattern, content, re.I).group(0)
                        ))

            except Exception:
                pass

        return findings

    # =========================================================================
    # Cryptographic Weakness Detection
    # =========================================================================

    async def analyze_crypto_weaknesses(self, root_path: Path) -> List[Finding]:
        """
        Check for cryptographic weaknesses.

        Checks for:
        - Weak key sizes
        - Deprecated algorithms (MD5, SHA1, DES, RC4)
        - Self-signed certificates
        - Default/shared SSL keys
        - Hardcoded encryption keys
        """
        self._log("[*] Analyzing cryptographic configurations...")
        findings = []

        # Check SSL/TLS certificates
        findings.extend(await self._check_certificates(root_path))

        # Check for weak crypto in configs
        findings.extend(await self._check_weak_crypto_configs(root_path))

        # Check for default/shared SSH host keys
        findings.extend(await self._check_default_ssh_keys(root_path))

        # Check for hardcoded encryption keys
        findings.extend(await self._check_hardcoded_crypto_keys(root_path))

        return findings

    async def _check_certificates(self, root_path: Path) -> List[Finding]:
        """Check SSL certificates for issues"""
        findings = []

        cert_patterns = [
            "etc/ssl/certs/*.pem",
            "etc/ssl/certs/*.crt",
            "etc/ssl/private/*.key",
            "etc/nginx/ssl/*",
            "etc/apache2/ssl/*",
            "etc/pki/**/*.pem",
            "etc/pki/**/*.crt",
            "usr/share/ca-certificates/**/*.crt",
        ]

        for pattern in cert_patterns:
            for cert_file in root_path.glob(pattern):
                if not cert_file.is_file():
                    continue

                try:
                    content = cert_file.read_text(errors="ignore")

                    # Check for self-signed certificate
                    if '-----BEGIN CERTIFICATE-----' in content:
                        # Try to detect self-signed by checking issuer == subject
                        cert_info = await self._get_cert_info(cert_file)
                        if cert_info:
                            if cert_info.get('self_signed'):
                                findings.append(Finding(
                                    severity=Severity.MEDIUM,
                                    category="crypto_weakness",
                                    title=f"Self-signed certificate: {cert_file.name}",
                                    description="Certificate is self-signed, may not be trusted by clients",
                                    file_path=cert_file.relative_to(root_path),
                                    matched_text="Self-signed"
                                ))

                            if cert_info.get('weak_key'):
                                findings.append(Finding(
                                    severity=Severity.HIGH,
                                    category="crypto_weakness",
                                    title=f"Weak key in certificate: {cert_file.name}",
                                    description=f"Certificate uses weak key: {cert_info.get('key_info', 'unknown')}",
                                    file_path=cert_file.relative_to(root_path),
                                    matched_text=cert_info.get('key_info', '')
                                ))

                except Exception:
                    pass

        return findings

    async def _get_cert_info(self, cert_file: Path) -> Optional[Dict]:
        """Get certificate information using openssl"""
        try:
            # Get certificate subject and issuer
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ['openssl', 'x509', '-in', str(cert_file), '-noout',
                     '-subject', '-issuer', '-text'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            )

            if result.returncode != 0:
                return None

            output = result.stdout
            info = {}

            # Check if self-signed (subject == issuer)
            subject_match = re.search(r'subject=(.+)', output)
            issuer_match = re.search(r'issuer=(.+)', output)
            if subject_match and issuer_match:
                subject = subject_match.group(1).strip()
                issuer = issuer_match.group(1).strip()
                info['self_signed'] = (subject == issuer)

            # Check key size
            if 'RSA Public-Key: (1024 bit)' in output or \
               'RSA Public-Key: (512 bit)' in output:
                info['weak_key'] = True
                info['key_info'] = 'RSA < 2048 bits'
            elif 'prime256v1' not in output and 'secp384r1' not in output:
                # Check for weak EC curves
                if 'EC PARAMETERS' in output and 'secp' not in output:
                    info['weak_key'] = True
                    info['key_info'] = 'Weak EC curve'

            return info

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    async def _check_weak_crypto_configs(self, root_path: Path) -> List[Finding]:
        """Check configuration files for weak crypto settings"""
        findings = []

        # Weak crypto patterns
        weak_patterns = [
            (r'cipher\s*[=:]\s*["\']?(des|rc4|md5|sha1)["\']?', Severity.HIGH,
             "Weak cipher algorithm"),
            (r'ssl[_-]?protocols?\s*[=:]\s*.*SSLv[23]', Severity.CRITICAL,
             "SSLv2/v3 enabled - vulnerable to POODLE"),
            (r'ssl[_-]?protocols?\s*[=:]\s*.*TLSv1\.0', Severity.HIGH,
             "TLSv1.0 enabled - considered weak"),
            (r'allow[_-]?md5\s*[=:]\s*(true|yes|1)', Severity.MEDIUM,
             "MD5 algorithm allowed"),
            (r'allow[_-]?sha1\s*[=:]\s*(true|yes|1)', Severity.MEDIUM,
             "SHA1 algorithm allowed for signatures"),
            (r'DHE?[-_]?EXPORT', Severity.CRITICAL,
             "Export-grade cryptography enabled - Logjam vulnerability"),
        ]

        config_files = list(root_path.glob("etc/**/*.conf")) + \
                       list(root_path.glob("etc/config/*"))

        for config_file in config_files:
            if not config_file.is_file():
                continue

            try:
                content = config_file.read_text(errors="ignore")

                for pattern, severity, description in weak_patterns:
                    match = re.search(pattern, content, re.I)
                    if match:
                        findings.append(Finding(
                            severity=severity,
                            category="crypto_weakness",
                            title=description,
                            description=f"Found in {config_file.name}",
                            file_path=config_file.relative_to(root_path),
                            matched_text=match.group(0)
                        ))

            except Exception:
                pass

        return findings

    async def _check_default_ssh_keys(self, root_path: Path) -> List[Finding]:
        """Check for default/shared SSH host keys"""
        findings = []

        ssh_key_paths = [
            "etc/ssh/ssh_host_rsa_key",
            "etc/ssh/ssh_host_dsa_key",
            "etc/ssh/ssh_host_ecdsa_key",
            "etc/ssh/ssh_host_ed25519_key",
            "etc/dropbear/dropbear_rsa_host_key",
            "etc/dropbear/dropbear_dss_host_key",
            "etc/dropbear/dropbear_ecdsa_host_key",
        ]

        # Known default key fingerprints (examples - would need real database)
        known_default_keys = {
            # These would be populated with known default key fingerprints
            # from vendor firmware
        }

        for key_path in ssh_key_paths:
            key_file = root_path / key_path
            if key_file.exists():
                try:
                    # Get key fingerprint
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda kf=key_file: subprocess.run(
                            ['ssh-keygen', '-lf', str(kf)],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                    )

                    if result.returncode == 0:
                        fingerprint = result.stdout.strip()

                        # Check against known defaults
                        for known_fp, device in known_default_keys.items():
                            if known_fp in fingerprint:
                                findings.append(Finding(
                                    severity=Severity.CRITICAL,
                                    category="crypto_weakness",
                                    title=f"Default SSH host key: {key_file.name}",
                                    description=f"SSH key matches known default from {device}",
                                    file_path=Path(key_path),
                                    matched_text=fingerprint
                                ))

                        # Check for weak key types
                        if 'DSA' in fingerprint or '1024' in fingerprint:
                            findings.append(Finding(
                                severity=Severity.HIGH,
                                category="crypto_weakness",
                                title=f"Weak SSH key: {key_file.name}",
                                description="DSA or 1024-bit RSA key - considered weak",
                                file_path=Path(key_path),
                                matched_text=fingerprint
                            ))

                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

        return findings

    async def _check_hardcoded_crypto_keys(self, root_path: Path) -> List[Finding]:
        """Check for hardcoded encryption keys in code/configs"""
        findings = []

        # Patterns for hardcoded keys
        hardcoded_patterns = [
            (r'aes[_-]?key\s*[=:]\s*["\']([0-9a-fA-F]{32,64})["\']', Severity.CRITICAL,
             "Hardcoded AES key"),
            (r'des[_-]?key\s*[=:]\s*["\']([0-9a-fA-F]{16})["\']', Severity.CRITICAL,
             "Hardcoded DES key"),
            (r'encryption[_-]?key\s*[=:]\s*["\']([^"\']{8,})["\']', Severity.HIGH,
             "Hardcoded encryption key"),
            (r'secret[_-]?key\s*[=:]\s*["\']([^"\']{16,})["\']', Severity.HIGH,
             "Hardcoded secret key"),
            (r'iv\s*[=:]\s*["\']([0-9a-fA-F]{16,32})["\']', Severity.HIGH,
             "Hardcoded IV (Initialization Vector)"),
        ]

        # Search in common locations
        search_patterns = [
            "etc/**/*.conf",
            "etc/config/*",
            "usr/lib/**/*.lua",
            "www/**/*.php",
            "var/www/**/*.php",
            "opt/**/*.py",
        ]

        for glob_pattern in search_patterns:
            for file_path in root_path.glob(glob_pattern):
                if not file_path.is_file() or file_path.stat().st_size > 1024 * 1024:
                    continue

                try:
                    content = file_path.read_text(errors="ignore")

                    for pattern, severity, description in hardcoded_patterns:
                        match = re.search(pattern, content, re.I)
                        if match:
                            findings.append(Finding(
                                severity=severity,
                                category="crypto_weakness",
                                title=description,
                                description=f"Found hardcoded cryptographic material",
                                file_path=file_path.relative_to(root_path),
                                matched_text=f"{description}: ***"
                            ))

                except Exception:
                    pass

        return findings
