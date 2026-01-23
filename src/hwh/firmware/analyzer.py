"""
Security Analyzer

Analyzes extracted firmware for security vulnerabilities including
hardcoded credentials, unsafe functions, and misconfigurations.
"""

import asyncio
import re
import os
import stat
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Callable, Dict, Set, Generator
import subprocess

from .patterns import (
    CREDENTIAL_PATTERNS,
    UNSAFE_FUNCTIONS,
    INTERESTING_FILES,
    INTERESTING_FILE_PATTERNS,
    INTERESTING_DIRS,
    BACKDOOR_PATTERNS,
    RISKY_SERVICE_PATTERNS,
    FINDING_SEVERITY,
)


class Severity(Enum):
    """Finding severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Finding:
    """A security finding from analysis"""
    severity: Severity
    category: str
    title: str
    description: str
    file_path: Optional[Path] = None
    line_number: Optional[int] = None
    matched_text: str = ""
    pattern_name: str = ""

    def __str__(self) -> str:
        loc = ""
        if self.file_path:
            loc = f" in {self.file_path}"
            if self.line_number:
                loc += f":{self.line_number}"
        return f"[{self.severity.value.upper()}] {self.title}{loc}"


@dataclass
class AnalysisResult:
    """Complete analysis results"""
    root_path: Path
    findings: List[Finding] = field(default_factory=list)
    files_scanned: int = 0
    binaries_analyzed: int = 0
    duration_seconds: float = 0.0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.LOW)


class SecurityAnalyzer:
    """
    Security analysis engine for extracted firmware.

    Scans for:
    - Hardcoded credentials and secrets
    - Unsafe C functions in binaries
    - Configuration issues
    - Known vulnerability patterns
    """

    # File size limits
    MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_BINARY_FILE_SIZE = 50 * 1024 * 1024  # 50MB

    # Binary file signatures
    ELF_MAGIC = b"\x7fELF"

    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None):
        self.progress_callback = progress_callback
        self.findings: List[Finding] = []
        self._scanned_files: Set[Path] = set()

    def _log(self, message: str) -> None:
        """Log a message via callback"""
        if self.progress_callback:
            self.progress_callback(message)

    def add_finding(self, finding: Finding) -> None:
        """Add a finding and log it"""
        self.findings.append(finding)
        self._log(str(finding))

    async def analyze_all(self, root_path: Path) -> AnalysisResult:
        """Run all security analyses on extracted filesystem"""
        import time
        start_time = time.time()

        self.findings = []
        self._scanned_files = set()

        self._log(f"[*] Starting security analysis of {root_path}")
        self._log("")

        # Run analyses
        await self.find_credentials(root_path)
        await self.analyze_configs(root_path)
        await self.find_interesting_files(root_path)
        await self.analyze_binaries(root_path)
        await self.check_permissions(root_path)

        duration = time.time() - start_time

        self._log("")
        self._log(f"[+] Analysis complete in {duration:.1f}s")
        self._log(f"[+] Files scanned: {len(self._scanned_files)}")
        self._log(f"[+] Findings: {len(self.findings)}")

        return AnalysisResult(
            root_path=root_path,
            findings=self.findings,
            files_scanned=len(self._scanned_files),
            duration_seconds=duration
        )

    async def find_credentials(self, root_path: Path) -> List[Finding]:
        """Search for hardcoded credentials and secrets"""
        self._log("[*] Scanning for credentials and secrets...")
        findings = []

        for file_path in self._iter_text_files(root_path):
            try:
                content = file_path.read_text(errors="ignore")
                self._scanned_files.add(file_path)

                for pattern_name, pattern in CREDENTIAL_PATTERNS.items():
                    for match in re.finditer(pattern, content):
                        # Calculate line number
                        line_num = content[:match.start()].count("\n") + 1
                        matched = match.group(0)[:100]  # Truncate long matches

                        severity_str = FINDING_SEVERITY.get(pattern_name, "medium")
                        severity = Severity(severity_str)

                        finding = Finding(
                            severity=severity,
                            category="credentials",
                            title=f"Potential {pattern_name.replace('_', ' ')}",
                            description=f"Found pattern matching {pattern_name}",
                            file_path=file_path.relative_to(root_path),
                            line_number=line_num,
                            matched_text=matched,
                            pattern_name=pattern_name
                        )
                        findings.append(finding)
                        self.add_finding(finding)

            except Exception:
                pass

        # Also check backdoor patterns
        for file_path in self._iter_text_files(root_path):
            try:
                content = file_path.read_text(errors="ignore")

                for pattern_name, pattern in BACKDOOR_PATTERNS.items():
                    for match in re.finditer(pattern, content):
                        line_num = content[:match.start()].count("\n") + 1

                        finding = Finding(
                            severity=Severity.HIGH,
                            category="backdoor",
                            title=f"Potential backdoor: {pattern_name}",
                            description="Possible hardcoded backdoor credentials",
                            file_path=file_path.relative_to(root_path),
                            line_number=line_num,
                            matched_text=match.group(0)[:100],
                            pattern_name=pattern_name
                        )
                        findings.append(finding)
                        self.add_finding(finding)

            except Exception:
                pass

        return findings

    async def analyze_configs(self, root_path: Path) -> List[Finding]:
        """Analyze configuration files for security issues"""
        self._log("[*] Analyzing configuration files...")
        findings = []

        for file_path in self._iter_text_files(root_path):
            # Check if it's a config file
            if not any(file_path.match(p) for p in ["*.conf", "*.cfg", "*.config", "*.ini"]):
                continue

            try:
                content = file_path.read_text(errors="ignore")
                self._scanned_files.add(file_path)

                for pattern_name, pattern in RISKY_SERVICE_PATTERNS.items():
                    for match in re.finditer(pattern, content):
                        line_num = content[:match.start()].count("\n") + 1

                        finding = Finding(
                            severity=Severity.MEDIUM,
                            category="configuration",
                            title=f"Risky config: {pattern_name.replace('_', ' ')}",
                            description=f"Potentially insecure configuration setting",
                            file_path=file_path.relative_to(root_path),
                            line_number=line_num,
                            matched_text=match.group(0)[:100],
                            pattern_name=pattern_name
                        )
                        findings.append(finding)
                        self.add_finding(finding)

            except Exception:
                pass

        return findings

    async def find_interesting_files(self, root_path: Path) -> List[Finding]:
        """Find files that commonly contain sensitive data"""
        self._log("[*] Looking for interesting files...")
        findings = []

        # Check for specific interesting files
        for interesting in INTERESTING_FILES:
            # Handle wildcards
            if "*" in interesting:
                pattern = interesting.lstrip("/")
                matches = list(root_path.glob(f"**/{pattern}"))
            else:
                # Direct path
                test_path = root_path / interesting.lstrip("/")
                matches = [test_path] if test_path.exists() else []

            for match in matches:
                if match.is_file():
                    finding = Finding(
                        severity=Severity.LOW,
                        category="interesting_file",
                        title=f"Sensitive file: {match.name}",
                        description=f"File commonly contains sensitive data",
                        file_path=match.relative_to(root_path)
                    )
                    findings.append(finding)
                    self.add_finding(finding)

        # Check for pattern matches
        for pattern in INTERESTING_FILE_PATTERNS:
            for match in root_path.rglob(pattern):
                if match.is_file() and match not in self._scanned_files:
                    self._scanned_files.add(match)
                    finding = Finding(
                        severity=Severity.LOW,
                        category="interesting_file",
                        title=f"Potentially sensitive: {match.name}",
                        description=f"File type ({pattern}) may contain sensitive data",
                        file_path=match.relative_to(root_path)
                    )
                    findings.append(finding)
                    # Don't log all of these, too noisy

        return findings

    async def analyze_binaries(self, root_path: Path) -> List[Finding]:
        """Analyze ELF binaries for unsafe functions"""
        self._log("[*] Analyzing binaries for unsafe functions...")
        findings = []

        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Check for ELF magic
            try:
                with open(file_path, "rb") as f:
                    magic = f.read(4)
                if magic != self.ELF_MAGIC:
                    continue
            except Exception:
                continue

            # Check file size
            if file_path.stat().st_size > self.MAX_BINARY_FILE_SIZE:
                continue

            self._scanned_files.add(file_path)

            # Extract strings and look for unsafe functions
            try:
                strings_output = await self._extract_strings(file_path)

                for unsafe in UNSAFE_FUNCTIONS:
                    if unsafe in strings_output:
                        finding = Finding(
                            severity=Severity.MEDIUM,
                            category="unsafe_function",
                            title=f"Unsafe function: {unsafe}()",
                            description=f"Binary uses potentially unsafe function {unsafe}",
                            file_path=file_path.relative_to(root_path),
                            pattern_name=unsafe
                        )
                        findings.append(finding)
                        self.add_finding(finding)

            except Exception:
                pass

        return findings

    async def check_permissions(self, root_path: Path) -> List[Finding]:
        """Check for permission issues in extracted filesystem"""
        self._log("[*] Checking file permissions...")
        findings = []

        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue

            try:
                mode = file_path.stat().st_mode

                # Check for world-writable files
                if mode & stat.S_IWOTH:
                    finding = Finding(
                        severity=Severity.LOW,
                        category="permissions",
                        title="World-writable file",
                        description="File is writable by all users",
                        file_path=file_path.relative_to(root_path)
                    )
                    findings.append(finding)
                    self.add_finding(finding)

                # Check for setuid/setgid binaries
                if mode & (stat.S_ISUID | stat.S_ISGID):
                    suid = "setuid" if mode & stat.S_ISUID else ""
                    sgid = "setgid" if mode & stat.S_ISGID else ""
                    perms = f"{suid} {sgid}".strip()

                    finding = Finding(
                        severity=Severity.MEDIUM,
                        category="permissions",
                        title=f"Privileged binary ({perms})",
                        description=f"Binary has {perms} bit set",
                        file_path=file_path.relative_to(root_path)
                    )
                    findings.append(finding)
                    self.add_finding(finding)

            except Exception:
                pass

        return findings

    async def search_pattern(
        self,
        root_path: Path,
        pattern: str,
        file_pattern: str = "*"
    ) -> List[Finding]:
        """Search for custom regex pattern in files"""
        self._log(f"[*] Searching for pattern: {pattern}")
        findings = []

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            self._log(f"[!] Invalid regex: {e}")
            return []

        for file_path in root_path.rglob(file_pattern):
            if not file_path.is_file():
                continue
            if file_path.stat().st_size > self.MAX_TEXT_FILE_SIZE:
                continue

            try:
                content = file_path.read_text(errors="ignore")
                self._scanned_files.add(file_path)

                for match in regex.finditer(content):
                    line_num = content[:match.start()].count("\n") + 1

                    finding = Finding(
                        severity=Severity.INFO,
                        category="search",
                        title=f"Pattern match",
                        description=f"Custom pattern matched",
                        file_path=file_path.relative_to(root_path),
                        line_number=line_num,
                        matched_text=match.group(0)[:100],
                        pattern_name=pattern
                    )
                    findings.append(finding)
                    self.add_finding(finding)

            except Exception:
                pass

        self._log(f"[+] Found {len(findings)} matches")
        return findings

    async def extract_strings(self, file_path: Path, min_length: int = 4) -> List[str]:
        """Extract printable strings from a file"""
        return (await self._extract_strings(file_path, min_length)).splitlines()

    async def _extract_strings(self, file_path: Path, min_length: int = 4) -> str:
        """Extract printable strings from a file using strings command"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["strings", f"-n{min_length}", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            )
            return result.stdout
        except Exception:
            # Fallback to manual extraction
            try:
                with open(file_path, "rb") as f:
                    data = f.read()

                strings = []
                current = []

                for byte in data:
                    if 32 <= byte <= 126:  # Printable ASCII
                        current.append(chr(byte))
                    else:
                        if len(current) >= min_length:
                            strings.append("".join(current))
                        current = []

                if len(current) >= min_length:
                    strings.append("".join(current))

                return "\n".join(strings)
            except Exception:
                return ""

    def _iter_text_files(self, root_path: Path) -> Generator[Path, None, None]:
        """Iterate over text files in the filesystem"""
        text_extensions = {
            ".txt", ".conf", ".cfg", ".config", ".ini", ".json", ".xml",
            ".yaml", ".yml", ".sh", ".bash", ".py", ".pl", ".php", ".lua",
            ".js", ".html", ".htm", ".css", ".sql", ".env", ".properties",
            ".plist", ".service", ".socket", ".timer", ".mount",
        }

        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip large files
            try:
                if file_path.stat().st_size > self.MAX_TEXT_FILE_SIZE:
                    continue
            except Exception:
                continue

            # Check extension
            if file_path.suffix.lower() in text_extensions:
                yield file_path
                continue

            # Check if it looks like a text file (no extension)
            if not file_path.suffix:
                try:
                    with open(file_path, "rb") as f:
                        sample = f.read(512)
                    # Check if mostly printable
                    printable = sum(32 <= b <= 126 or b in (9, 10, 13) for b in sample)
                    if len(sample) > 0 and printable / len(sample) > 0.8:
                        yield file_path
                except Exception:
                    pass

    def export_findings(self, output_path: Path, format: str = "txt") -> bool:
        """Export findings to file"""
        try:
            if format == "txt":
                return self._export_txt(output_path)
            elif format == "json":
                return self._export_json(output_path)
            elif format == "csv":
                return self._export_csv(output_path)
            else:
                return False
        except Exception as e:
            self._log(f"[!] Export failed: {e}")
            return False

    def _export_txt(self, output_path: Path) -> bool:
        """Export findings as text report"""
        lines = [
            "=" * 60,
            "FIRMWARE SECURITY ANALYSIS REPORT",
            "=" * 60,
            "",
            f"Total findings: {len(self.findings)}",
            f"  Critical: {sum(1 for f in self.findings if f.severity == Severity.CRITICAL)}",
            f"  High:     {sum(1 for f in self.findings if f.severity == Severity.HIGH)}",
            f"  Medium:   {sum(1 for f in self.findings if f.severity == Severity.MEDIUM)}",
            f"  Low:      {sum(1 for f in self.findings if f.severity == Severity.LOW)}",
            "",
            "=" * 60,
            "FINDINGS",
            "=" * 60,
            "",
        ]

        # Group by severity
        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            findings = [f for f in self.findings if f.severity == severity]
            if not findings:
                continue

            lines.append(f"--- {severity.value.upper()} ---")
            lines.append("")

            for finding in findings:
                lines.append(f"[{finding.category}] {finding.title}")
                if finding.file_path:
                    loc = str(finding.file_path)
                    if finding.line_number:
                        loc += f":{finding.line_number}"
                    lines.append(f"  Location: {loc}")
                if finding.matched_text:
                    lines.append(f"  Match: {finding.matched_text}")
                lines.append(f"  {finding.description}")
                lines.append("")

        output_path.write_text("\n".join(lines))
        return True

    def _export_json(self, output_path: Path) -> bool:
        """Export findings as JSON"""
        import json

        data = {
            "summary": {
                "total": len(self.findings),
                "critical": sum(1 for f in self.findings if f.severity == Severity.CRITICAL),
                "high": sum(1 for f in self.findings if f.severity == Severity.HIGH),
                "medium": sum(1 for f in self.findings if f.severity == Severity.MEDIUM),
                "low": sum(1 for f in self.findings if f.severity == Severity.LOW),
            },
            "findings": [
                {
                    "severity": f.severity.value,
                    "category": f.category,
                    "title": f.title,
                    "description": f.description,
                    "file_path": str(f.file_path) if f.file_path else None,
                    "line_number": f.line_number,
                    "matched_text": f.matched_text,
                }
                for f in self.findings
            ]
        }

        output_path.write_text(json.dumps(data, indent=2))
        return True

    def _export_csv(self, output_path: Path) -> bool:
        """Export findings as CSV"""
        import csv

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Severity", "Category", "Title", "Description",
                "File", "Line", "Match"
            ])

            for finding in self.findings:
                writer.writerow([
                    finding.severity.value,
                    finding.category,
                    finding.title,
                    finding.description,
                    str(finding.file_path) if finding.file_path else "",
                    finding.line_number or "",
                    finding.matched_text,
                ])

        return True
