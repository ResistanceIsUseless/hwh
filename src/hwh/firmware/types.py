"""
Common types for firmware analysis
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


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
