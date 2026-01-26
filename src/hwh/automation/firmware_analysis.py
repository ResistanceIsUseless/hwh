"""
Automated Firmware Analysis

Pipeline for extracting and analyzing firmware:
1. Read flash → detect filesystem → extract
2. Scan for secrets (credentials, keys, certificates)
3. Identify interesting files and functions
"""

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Callable, Set
from dataclasses import dataclass, field
from enum import Enum


class FindingType(Enum):
    """Types of security-relevant findings."""
    CREDENTIAL = "credential"
    API_KEY = "api_key"
    PRIVATE_KEY = "private_key"
    CERTIFICATE = "certificate"
    SSH_KEY = "ssh_key"
    PASSWORD_HASH = "password_hash"
    HARDCODED_IP = "hardcoded_ip"
    DEBUG_STRING = "debug_string"
    INTERESTING_FILE = "interesting_file"
    SYMBOL = "symbol"
    URL = "url"


@dataclass
class Finding:
    """A security-relevant finding in firmware."""
    finding_type: FindingType
    file_path: str
    line_number: int = 0
    content: str = ""
    context: str = ""
    severity: str = "medium"  # low, medium, high, critical
    metadata: Dict = field(default_factory=dict)

    def __repr__(self):
        return f"[{self.severity.upper()}] {self.finding_type.value}: {self.content[:50]}... in {self.file_path}"


@dataclass
class AnalysisReport:
    """Complete firmware analysis report."""
    firmware_path: str
    firmware_size: int = 0
    filesystem_type: str = ""
    extraction_path: str = ""
    file_count: int = 0
    findings: List[Finding] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def findings_by_type(self, finding_type: FindingType) -> List[Finding]:
        return [f for f in self.findings if f.finding_type == finding_type]

    def findings_by_severity(self, severity: str) -> List[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def summary(self) -> str:
        lines = [
            "Firmware Analysis Report",
            "=" * 50,
            f"Firmware: {self.firmware_path}",
            f"Size: {self.firmware_size:,} bytes",
            f"Filesystem: {self.filesystem_type}",
            f"Files extracted: {self.file_count}",
            f"Total findings: {len(self.findings)}",
            "",
            "Findings by severity:",
        ]

        for sev in ["critical", "high", "medium", "low"]:
            count = len(self.findings_by_severity(sev))
            if count > 0:
                lines.append(f"  {sev.upper()}: {count}")

        lines.append("")
        lines.append("Findings by type:")
        type_counts = {}
        for f in self.findings:
            type_counts[f.finding_type.value] = type_counts.get(f.finding_type.value, 0) + 1
        for ftype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {ftype}: {count}")

        if self.findings:
            lines.append("")
            lines.append("Top findings:")
            for f in sorted(self.findings, key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}[x.severity])[:10]:
                lines.append(f"  {f}")

        return "\n".join(lines)

    def save(self, path: str):
        """Save report to JSON file."""
        import json
        data = {
            'firmware_path': self.firmware_path,
            'firmware_size': self.firmware_size,
            'filesystem_type': self.filesystem_type,
            'extraction_path': self.extraction_path,
            'file_count': self.file_count,
            'metadata': self.metadata,
            'findings': [
                {
                    'type': f.finding_type.value,
                    'file': f.file_path,
                    'line': f.line_number,
                    'content': f.content,
                    'context': f.context,
                    'severity': f.severity,
                    'metadata': f.metadata,
                }
                for f in self.findings
            ]
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)


# Regex patterns for finding secrets
SECRET_PATTERNS = {
    FindingType.PASSWORD_HASH: [
        r'\$[156]\$[a-zA-Z0-9./]+\$[a-zA-Z0-9./]+',  # Unix crypt
        r'[a-f0-9]{32}',  # MD5
        r'[a-f0-9]{40}',  # SHA1
        r'[a-f0-9]{64}',  # SHA256
    ],
    FindingType.API_KEY: [
        r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        r'(?i)(access[_-]?token)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        r'AIza[0-9A-Za-z_-]{35}',  # Google API key
        r'AKIA[0-9A-Z]{16}',  # AWS access key
    ],
    FindingType.CREDENTIAL: [
        r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?([^\s"\']{4,})["\']?',
        r'(?i)(username|user)\s*[=:]\s*["\']?([^\s"\']{3,})["\']?',
        r'(?i)(admin|root):[^\s:]+',  # User:pass format
    ],
    FindingType.PRIVATE_KEY: [
        r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
        r'-----BEGIN PGP PRIVATE KEY BLOCK-----',
    ],
    FindingType.CERTIFICATE: [
        r'-----BEGIN CERTIFICATE-----',
        r'-----BEGIN X509 CERTIFICATE-----',
    ],
    FindingType.SSH_KEY: [
        r'ssh-(rsa|dss|ed25519|ecdsa)\s+[A-Za-z0-9+/]+[=]*',
    ],
    FindingType.HARDCODED_IP: [
        r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
    ],
    FindingType.URL: [
        r'https?://[^\s<>"\']+',
    ],
    FindingType.DEBUG_STRING: [
        r'(?i)(debug|verbose|test)\s*[=:]\s*(true|1|on)',
        r'(?i)#define\s+DEBUG\s+1',
        r'(?i)ENABLE_DEBUG',
    ],
}

# Interesting file patterns
INTERESTING_FILES = {
    'config': [
        r'.*\.conf$', r'.*\.cfg$', r'.*\.ini$', r'.*\.json$', r'.*\.yaml$', r'.*\.yml$',
        r'.*config.*', r'.*settings.*',
    ],
    'credentials': [
        r'.*/etc/passwd$', r'.*/etc/shadow$', r'.*/etc/group$',
        r'.*\.pem$', r'.*\.key$', r'.*\.crt$', r'.*\.p12$', r'.*\.pfx$',
        r'.*/\.ssh/.*', r'.*id_rsa.*', r'.*id_dsa.*', r'.*authorized_keys$',
        r'.*\.htpasswd$', r'.*\.netrc$',
    ],
    'database': [
        r'.*\.db$', r'.*\.sqlite.*', r'.*\.sql$',
    ],
    'script': [
        r'.*/etc/init\.d/.*', r'.*/etc/rc\.d/.*',
        r'.*startup.*\.sh$', r'.*boot.*\.sh$',
        r'.*\.cgi$', r'.*\.php$', r'.*\.asp$',
    ],
    'binary': [
        r'.*/bin/.*', r'.*/sbin/.*', r'.*/usr/bin/.*',
        r'.*busybox.*', r'.*dropbear.*', r'.*telnetd.*', r'.*httpd.*',
    ],
}


class FirmwareAnalyzer:
    """
    Automated firmware extraction and analysis.

    Pipeline:
    1. Extract firmware using binwalk/sasquatch
    2. Scan all text files for secrets
    3. Identify interesting files
    4. Extract symbols from binaries
    5. Generate report

    Example:
        >>> analyzer = FirmwareAnalyzer()
        >>> report = await analyzer.analyze("firmware.bin")
        >>> print(report.summary())
        >>> report.save("analysis_report.json")
    """

    def __init__(
        self,
        output_dir: str = "/tmp/firmware_analysis",
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.output_dir = Path(output_dir)
        self.log = log_callback or print
        self._stop = False

    async def analyze(
        self,
        firmware_path: str,
        extract: bool = True,
        scan_secrets: bool = True,
        find_interesting: bool = True,
        extract_symbols: bool = True
    ) -> AnalysisReport:
        """
        Run full firmware analysis.

        Args:
            firmware_path: Path to firmware file
            extract: Extract filesystem contents
            scan_secrets: Scan for hardcoded secrets
            find_interesting: Find interesting files
            extract_symbols: Extract symbols from binaries

        Returns:
            AnalysisReport with all findings
        """
        firmware_path = Path(firmware_path)
        if not firmware_path.exists():
            raise FileNotFoundError(f"Firmware not found: {firmware_path}")

        report = AnalysisReport(
            firmware_path=str(firmware_path),
            firmware_size=firmware_path.stat().st_size
        )

        self.log(f"[Analysis] Starting analysis of {firmware_path.name}")
        self.log(f"           Size: {report.firmware_size:,} bytes")

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        extract_dir = self.output_dir / firmware_path.stem

        # Step 1: Extract firmware
        if extract:
            self.log("[Analysis] Step 1: Extracting firmware...")
            fs_type = await self._extract_firmware(firmware_path, extract_dir)
            report.filesystem_type = fs_type
            report.extraction_path = str(extract_dir)

            # Count files
            if extract_dir.exists():
                report.file_count = sum(1 for _ in extract_dir.rglob("*") if _.is_file())
                self.log(f"           Extracted {report.file_count} files")

        # Step 2: Scan for secrets
        if scan_secrets and extract_dir.exists():
            self.log("[Analysis] Step 2: Scanning for secrets...")
            secret_findings = await self._scan_for_secrets(extract_dir)
            report.findings.extend(secret_findings)
            self.log(f"           Found {len(secret_findings)} potential secrets")

        # Step 3: Find interesting files
        if find_interesting and extract_dir.exists():
            self.log("[Analysis] Step 3: Finding interesting files...")
            file_findings = await self._find_interesting_files(extract_dir)
            report.findings.extend(file_findings)
            self.log(f"           Found {len(file_findings)} interesting files")

        # Step 4: Extract symbols
        if extract_symbols and extract_dir.exists():
            self.log("[Analysis] Step 4: Extracting symbols from binaries...")
            symbol_findings = await self._extract_symbols(extract_dir)
            report.findings.extend(symbol_findings)
            self.log(f"           Found {len(symbol_findings)} interesting symbols")

        self.log(f"[Analysis] Complete: {len(report.findings)} total findings")
        return report

    async def _extract_firmware(self, firmware_path: Path, extract_dir: Path) -> str:
        """Extract firmware using binwalk."""
        try:
            # Try binwalk extraction
            result = subprocess.run(
                ["binwalk", "-e", "-C", str(extract_dir.parent), str(firmware_path)],
                capture_output=True,
                text=True,
                timeout=300
            )

            # Detect filesystem type from binwalk output
            fs_type = "unknown"
            if "squashfs" in result.stdout.lower():
                fs_type = "squashfs"
            elif "jffs2" in result.stdout.lower():
                fs_type = "jffs2"
            elif "cramfs" in result.stdout.lower():
                fs_type = "cramfs"
            elif "romfs" in result.stdout.lower():
                fs_type = "romfs"
            elif "ext" in result.stdout.lower():
                fs_type = "ext"
            elif "tar" in result.stdout.lower():
                fs_type = "tar"

            return fs_type

        except subprocess.TimeoutExpired:
            self.log("[Analysis] Extraction timed out")
            return "timeout"
        except FileNotFoundError:
            self.log("[Analysis] binwalk not found, trying manual extraction")
            return await self._manual_extract(firmware_path, extract_dir)
        except Exception as e:
            self.log(f"[Analysis] Extraction error: {e}")
            return "error"

    async def _manual_extract(self, firmware_path: Path, extract_dir: Path) -> str:
        """Manual extraction fallback."""
        # Try common extraction tools
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Read magic bytes
        with open(firmware_path, 'rb') as f:
            magic = f.read(8)

        # Try to identify and extract
        if magic[:4] == b'hsqs' or magic[:4] == b'sqsh':
            # SquashFS
            try:
                subprocess.run(
                    ["unsquashfs", "-d", str(extract_dir), str(firmware_path)],
                    capture_output=True,
                    timeout=300
                )
                return "squashfs"
            except Exception:
                pass

        elif magic[:2] == b'\x1f\x8b':
            # Gzip
            try:
                subprocess.run(
                    ["tar", "-xzf", str(firmware_path), "-C", str(extract_dir)],
                    capture_output=True,
                    timeout=300
                )
                return "tar.gz"
            except Exception:
                pass

        return "unknown"

    async def _scan_for_secrets(self, extract_dir: Path) -> List[Finding]:
        """Scan files for hardcoded secrets."""
        findings = []
        text_extensions = {'.txt', '.conf', '.cfg', '.ini', '.json', '.xml', '.yaml', '.yml',
                         '.sh', '.bash', '.py', '.php', '.js', '.html', '.htm', '.c', '.h',
                         '.cpp', '.hpp', '.java', '.properties', '.env', ''}

        for file_path in extract_dir.rglob("*"):
            if self._stop:
                break

            if not file_path.is_file():
                continue

            # Check if text file
            if file_path.suffix.lower() not in text_extensions:
                continue

            # Skip large files
            try:
                if file_path.stat().st_size > 1_000_000:  # 1MB
                    continue
            except Exception:
                continue

            # Read and scan file
            try:
                with open(file_path, 'r', errors='ignore') as f:
                    content = f.read()

                for finding_type, patterns in SECRET_PATTERNS.items():
                    for pattern in patterns:
                        for match in re.finditer(pattern, content):
                            # Get line number
                            line_num = content[:match.start()].count('\n') + 1

                            # Get context
                            lines = content.split('\n')
                            start_line = max(0, line_num - 2)
                            end_line = min(len(lines), line_num + 1)
                            context = '\n'.join(lines[start_line:end_line])

                            # Determine severity
                            severity = self._classify_severity(finding_type, match.group())

                            findings.append(Finding(
                                finding_type=finding_type,
                                file_path=str(file_path.relative_to(extract_dir)),
                                line_number=line_num,
                                content=match.group()[:100],
                                context=context[:200],
                                severity=severity
                            ))

            except Exception:
                pass

        return findings

    async def _find_interesting_files(self, extract_dir: Path) -> List[Finding]:
        """Find files that are commonly interesting for security analysis."""
        findings = []

        for file_path in extract_dir.rglob("*"):
            if self._stop:
                break

            if not file_path.is_file():
                continue

            rel_path = str(file_path.relative_to(extract_dir))

            for category, patterns in INTERESTING_FILES.items():
                for pattern in patterns:
                    if re.match(pattern, rel_path, re.IGNORECASE):
                        severity = "high" if category in ("credentials", "database") else "medium"

                        findings.append(Finding(
                            finding_type=FindingType.INTERESTING_FILE,
                            file_path=rel_path,
                            content=f"Interesting {category} file",
                            severity=severity,
                            metadata={'category': category, 'size': file_path.stat().st_size}
                        ))
                        break

        return findings

    async def _extract_symbols(self, extract_dir: Path) -> List[Finding]:
        """Extract symbols from ELF binaries."""
        findings = []
        interesting_symbols = {
            'debug', 'test', 'backdoor', 'password', 'secret', 'admin', 'root',
            'shell', 'exec', 'system', 'popen', 'eval', 'crypto', 'decrypt',
            'encrypt', 'key', 'auth', 'login', 'bypass', 'check', 'verify'
        }

        for file_path in extract_dir.rglob("*"):
            if self._stop:
                break

            if not file_path.is_file():
                continue

            # Check if ELF
            try:
                with open(file_path, 'rb') as f:
                    if f.read(4) != b'\x7fELF':
                        continue
            except Exception:
                continue

            # Extract symbols using nm or strings
            try:
                result = subprocess.run(
                    ["strings", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                for line in result.stdout.split('\n'):
                    line_lower = line.lower()
                    for symbol in interesting_symbols:
                        if symbol in line_lower and len(line) > 5 and len(line) < 100:
                            findings.append(Finding(
                                finding_type=FindingType.SYMBOL,
                                file_path=str(file_path.relative_to(extract_dir)),
                                content=line[:100],
                                severity="low",
                                metadata={'matched_symbol': symbol}
                            ))
                            break

            except Exception:
                pass

        return findings

    def _classify_severity(self, finding_type: FindingType, content: str) -> str:
        """Classify finding severity."""
        if finding_type == FindingType.PRIVATE_KEY:
            return "critical"
        elif finding_type == FindingType.SSH_KEY:
            return "critical"
        elif finding_type == FindingType.CREDENTIAL:
            if any(word in content.lower() for word in ['admin', 'root', 'password']):
                return "high"
            return "medium"
        elif finding_type == FindingType.API_KEY:
            return "high"
        elif finding_type == FindingType.PASSWORD_HASH:
            return "high"
        elif finding_type == FindingType.CERTIFICATE:
            return "medium"
        elif finding_type == FindingType.DEBUG_STRING:
            return "low"
        elif finding_type == FindingType.HARDCODED_IP:
            # Private IPs are less interesting
            if content.startswith(('192.168.', '10.', '172.16.')):
                return "low"
            return "medium"
        elif finding_type == FindingType.URL:
            return "low"

        return "medium"

    def stop(self):
        """Stop analysis."""
        self._stop = True


async def analyze_firmware(
    firmware_path: str,
    output_dir: str = "/tmp/firmware_analysis",
    log_callback: Optional[Callable[[str], None]] = None
) -> AnalysisReport:
    """
    Convenience function for firmware analysis.

    Args:
        firmware_path: Path to firmware file
        output_dir: Directory for extracted files
        log_callback: Logging callback

    Returns:
        AnalysisReport with findings
    """
    analyzer = FirmwareAnalyzer(output_dir=output_dir, log_callback=log_callback)
    return await analyzer.analyze(firmware_path)
