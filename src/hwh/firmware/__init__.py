"""
hwh Firmware Analysis Module

Tools for extracting, analyzing, and searching firmware images
for security vulnerabilities.
"""

from .extractor import FirmwareExtractor, FilesystemEntry
from .analyzer import SecurityAnalyzer, Finding, Severity
from .patterns import (
    CREDENTIAL_PATTERNS,
    UNSAFE_FUNCTIONS,
    INTERESTING_FILES,
    INTERESTING_DIRS,
)

__all__ = [
    "FirmwareExtractor",
    "FilesystemEntry",
    "SecurityAnalyzer",
    "Finding",
    "Severity",
    "CREDENTIAL_PATTERNS",
    "UNSAFE_FUNCTIONS",
    "INTERESTING_FILES",
    "INTERESTING_DIRS",
]
