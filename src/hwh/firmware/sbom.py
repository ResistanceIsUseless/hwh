"""
Software Bill of Materials (SBOM) Generation

Generates SBOM in SPDX format for firmware analysis.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from .analyzer_advanced import SoftwarePackage


@dataclass
class SBOMPackage:
    """Package information for SBOM"""
    name: str
    version: str
    supplier: str = "Unknown"
    download_location: str = "NOASSERTION"
    files_analyzed: bool = False
    license_concluded: str = "NOASSERTION"
    license_declared: str = "NOASSERTION"
    copyright_text: str = "NOASSERTION"
    external_refs: List[Dict] = field(default_factory=list)
    checksums: List[Dict] = field(default_factory=list)
    description: str = ""


@dataclass
class SBOMFile:
    """File information for SBOM"""
    name: str
    spdx_id: str
    checksums: List[Dict]
    license_concluded: str = "NOASSERTION"
    copyright_text: str = "NOASSERTION"
    file_types: List[str] = field(default_factory=list)


class SBOMGenerator:
    """
    Generate Software Bill of Materials in SPDX format.

    Supports:
    - SPDX 2.3 JSON format
    - Package enumeration from opkg/dpkg
    - File checksums (SHA256, SHA1, MD5)
    - License detection
    - CPE/PURL references for vulnerability correlation
    """

    def __init__(self, firmware_name: str = "Unknown Firmware"):
        self.firmware_name = firmware_name
        self.packages: List[SBOMPackage] = []
        self.files: List[SBOMFile] = []
        self.namespace = f"https://hwh.tool/spdx/{uuid.uuid4()}"
        self.document_name = f"SBOM-{firmware_name}"

    def add_package(self, pkg: SoftwarePackage) -> None:
        """Add a package from firmware analysis"""
        sbom_pkg = SBOMPackage(
            name=pkg.name,
            version=pkg.version,
            supplier=f"PackageManager: {pkg.source}",
        )

        # Add CPE reference if we can construct one
        cpe = self._generate_cpe(pkg.name, pkg.version)
        if cpe:
            sbom_pkg.external_refs.append({
                "referenceCategory": "SECURITY",
                "referenceType": "cpe23Type",
                "referenceLocator": cpe
            })

        # Add PURL reference
        purl = self._generate_purl(pkg.name, pkg.version, pkg.source)
        if purl:
            sbom_pkg.external_refs.append({
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": purl
            })

        self.packages.append(sbom_pkg)

    def add_packages_from_analysis(self, packages: List[SoftwarePackage]) -> None:
        """Add multiple packages from firmware analysis"""
        for pkg in packages:
            self.add_package(pkg)

    def add_file(self, file_path: Path, root_path: Path) -> None:
        """Add a file to the SBOM"""
        try:
            rel_path = file_path.relative_to(root_path)
            content = file_path.read_bytes()

            checksums = [
                {"algorithm": "SHA256", "checksumValue": hashlib.sha256(content).hexdigest()},
                {"algorithm": "SHA1", "checksumValue": hashlib.sha1(content).hexdigest()},
                {"algorithm": "MD5", "checksumValue": hashlib.md5(content).hexdigest()},
            ]

            # Determine file types
            file_types = self._detect_file_types(file_path, content)

            sbom_file = SBOMFile(
                name=str(rel_path),
                spdx_id=f"SPDXRef-File-{self._sanitize_spdx_id(str(rel_path))}",
                checksums=checksums,
                file_types=file_types,
            )

            self.files.append(sbom_file)

        except Exception:
            pass

    def scan_directory(self, root_path: Path, max_files: int = 1000) -> None:
        """Scan directory and add files to SBOM"""
        count = 0
        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue
            if count >= max_files:
                break

            # Skip very large files
            try:
                if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
                    continue
            except OSError:
                continue

            self.add_file(file_path, root_path)
            count += 1

    def generate_spdx_json(self) -> Dict[str, Any]:
        """Generate SPDX 2.3 JSON format SBOM"""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        sbom = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": self.document_name,
            "documentNamespace": self.namespace,
            "creationInfo": {
                "created": now,
                "creators": [
                    "Tool: hwh-firmware-analyzer",
                    "Organization: hwh"
                ],
                "licenseListVersion": "3.19"
            },
            "packages": [],
            "files": [],
            "relationships": []
        }

        # Add document describes relationship
        pkg_refs = []

        # Add packages
        for i, pkg in enumerate(self.packages):
            spdx_id = f"SPDXRef-Package-{self._sanitize_spdx_id(pkg.name)}-{i}"
            pkg_refs.append(spdx_id)

            pkg_data = {
                "SPDXID": spdx_id,
                "name": pkg.name,
                "versionInfo": pkg.version,
                "supplier": pkg.supplier,
                "downloadLocation": pkg.download_location,
                "filesAnalyzed": pkg.files_analyzed,
                "licenseConcluded": pkg.license_concluded,
                "licenseDeclared": pkg.license_declared,
                "copyrightText": pkg.copyright_text,
            }

            if pkg.external_refs:
                pkg_data["externalRefs"] = pkg.external_refs

            if pkg.checksums:
                pkg_data["checksums"] = pkg.checksums

            if pkg.description:
                pkg_data["description"] = pkg.description

            sbom["packages"].append(pkg_data)

        # Add files
        for f in self.files:
            file_data = {
                "SPDXID": f.spdx_id,
                "fileName": f.name,
                "checksums": f.checksums,
                "licenseConcluded": f.license_concluded,
                "copyrightText": f.copyright_text,
            }

            if f.file_types:
                file_data["fileTypes"] = f.file_types

            sbom["files"].append(file_data)

        # Add document describes relationship
        for ref in pkg_refs:
            sbom["relationships"].append({
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": ref
            })

        return sbom

    def export_spdx_json(self, output_path: Path) -> bool:
        """Export SBOM to SPDX JSON file"""
        try:
            sbom = self.generate_spdx_json()
            with open(output_path, 'w') as f:
                json.dump(sbom, f, indent=2)
            return True
        except Exception:
            return False

    def export_spdx_tv(self, output_path: Path) -> bool:
        """Export SBOM to SPDX Tag-Value format"""
        try:
            sbom = self.generate_spdx_json()
            lines = []

            # Document info
            lines.append(f"SPDXVersion: {sbom['spdxVersion']}")
            lines.append(f"DataLicense: {sbom['dataLicense']}")
            lines.append(f"SPDXID: {sbom['SPDXID']}")
            lines.append(f"DocumentName: {sbom['name']}")
            lines.append(f"DocumentNamespace: {sbom['documentNamespace']}")
            lines.append(f"Creator: {sbom['creationInfo']['creators'][0]}")
            lines.append(f"Created: {sbom['creationInfo']['created']}")
            lines.append("")

            # Packages
            for pkg in sbom['packages']:
                lines.append(f"PackageName: {pkg['name']}")
                lines.append(f"SPDXID: {pkg['SPDXID']}")
                lines.append(f"PackageVersion: {pkg['versionInfo']}")
                lines.append(f"PackageSupplier: {pkg['supplier']}")
                lines.append(f"PackageDownloadLocation: {pkg['downloadLocation']}")
                lines.append(f"FilesAnalyzed: {str(pkg['filesAnalyzed']).lower()}")
                lines.append(f"PackageLicenseConcluded: {pkg['licenseConcluded']}")
                lines.append(f"PackageLicenseDeclared: {pkg['licenseDeclared']}")
                lines.append(f"PackageCopyrightText: {pkg['copyrightText']}")

                for ref in pkg.get('externalRefs', []):
                    lines.append(f"ExternalRef: {ref['referenceCategory']} {ref['referenceType']} {ref['referenceLocator']}")

                lines.append("")

            # Files
            for f in sbom['files']:
                lines.append(f"FileName: {f['fileName']}")
                lines.append(f"SPDXID: {f['spdxId']}")
                for cs in f['checksums']:
                    lines.append(f"FileChecksum: {cs['algorithm']}: {cs['checksumValue']}")
                lines.append(f"LicenseConcluded: {f['licenseConcluded']}")
                lines.append(f"FileCopyrightText: {f['copyrightText']}")
                lines.append("")

            with open(output_path, 'w') as f:
                f.write('\n'.join(lines))
            return True

        except Exception:
            return False

    def _generate_cpe(self, name: str, version: str) -> Optional[str]:
        """Generate CPE 2.3 string for package"""
        # Simplified CPE generation - would need vendor database for accuracy
        name_clean = name.lower().replace(' ', '_')
        version_clean = version.replace(' ', '_')
        return f"cpe:2.3:a:*:{name_clean}:{version_clean}:*:*:*:*:*:*:*"

    def _generate_purl(self, name: str, version: str, source: str) -> Optional[str]:
        """Generate Package URL for package"""
        # Map package manager to PURL type
        purl_types = {
            'opkg': 'openwrt',
            'dpkg': 'deb',
            'rpm': 'rpm',
        }
        purl_type = purl_types.get(source, 'generic')
        return f"pkg:{purl_type}/{name}@{version}"

    def _sanitize_spdx_id(self, name: str) -> str:
        """Sanitize string for use in SPDX ID"""
        import re
        # SPDX IDs can only contain letters, numbers, and dots
        return re.sub(r'[^a-zA-Z0-9.]', '-', name)

    def _detect_file_types(self, file_path: Path, content: bytes) -> List[str]:
        """Detect file types for SPDX"""
        types = []

        suffix = file_path.suffix.lower()

        # Source code
        if suffix in ['.c', '.h', '.cpp', '.hpp', '.cc', '.cxx']:
            types.append("SOURCE")
        elif suffix in ['.py', '.js', '.ts', '.go', '.rs', '.java', '.lua', '.php']:
            types.append("SOURCE")
        elif suffix in ['.sh', '.bash']:
            types.append("SOURCE")
            types.append("TEXT")

        # Binary
        if content[:4] == b'\x7fELF':
            types.append("BINARY")
        elif content[:2] == b'MZ':
            types.append("BINARY")

        # Documentation
        if suffix in ['.md', '.txt', '.rst', '.html', '.htm']:
            types.append("DOCUMENTATION")
            types.append("TEXT")

        # Config
        if suffix in ['.conf', '.cfg', '.ini', '.yaml', '.yml', '.json', '.xml']:
            types.append("TEXT")

        # Archive
        if suffix in ['.tar', '.gz', '.bz2', '.xz', '.zip', '.rar', '.7z']:
            types.append("ARCHIVE")

        # Image
        if suffix in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.ico']:
            types.append("IMAGE")

        if not types:
            types.append("OTHER")

        return types


async def generate_sbom(
    root_path: Path,
    packages: List[SoftwarePackage],
    firmware_name: str = "Unknown",
    include_files: bool = True,
    max_files: int = 500
) -> SBOMGenerator:
    """
    Generate SBOM from firmware analysis results.

    Args:
        root_path: Path to extracted firmware root
        packages: List of detected software packages
        firmware_name: Name of firmware for SBOM document
        include_files: Whether to include file checksums
        max_files: Maximum number of files to include

    Returns:
        SBOMGenerator instance with populated data
    """
    generator = SBOMGenerator(firmware_name)

    # Add packages
    generator.add_packages_from_analysis(packages)

    # Optionally add files
    if include_files:
        generator.scan_directory(root_path, max_files)

    return generator
