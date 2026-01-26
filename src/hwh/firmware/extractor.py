"""
Firmware Extractor

Extracts filesystems from firmware images using binwalk for scanning
and specialized tools for extraction.

Based on firmware_extract.py - uses binwalk only for scanning, then
extracts with dedicated tools to avoid recursive folder chaos.
"""

import asyncio
import struct
import shutil
import subprocess
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

# Debug flag - set to True for verbose output
DEBUG = True


class FilesystemType(Enum):
    """Supported filesystem types"""
    SQUASHFS = "squashfs"
    JFFS2 = "jffs2"
    UBIFS = "ubifs"
    CRAMFS = "cramfs"
    CPIO = "cpio"
    COMPRESSED = "compressed"
    UNKNOWN = "unknown"


@dataclass
class FilesystemEntry:
    """A detected filesystem in a firmware image"""
    offset: int
    size: Optional[int]
    fs_type: FilesystemType
    description: str
    extracted: bool = False
    extract_path: Optional[Path] = None


@dataclass
class ExtractionResult:
    """Result of a firmware extraction"""
    success: bool
    firmware_path: Path
    output_dir: Path
    filesystems: List[FilesystemEntry] = field(default_factory=list)
    extracted_count: int = 0
    total_files: int = 0
    error: Optional[str] = None


class FirmwareExtractor:
    """
    Firmware extraction engine.

    Uses binwalk for scanning to identify embedded filesystems,
    then extracts them using specialized tools (sasquatch, jefferson, etc.)

    Supports both binwalk v2.x (-B flag) and v3.x (no flag) CLI interfaces.
    """

    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None):
        self.progress_callback = progress_callback
        self.firmware_path: Optional[Path] = None
        self.output_dir: Optional[Path] = None
        self.filesystems: List[FilesystemEntry] = []
        self._tools: Dict[str, Optional[str]] = {}
        self._binwalk_version: Optional[int] = None  # 2 or 3

    def _log(self, message: str) -> None:
        """Log a message via callback"""
        if self.progress_callback:
            self.progress_callback(message)

    def _debug(self, message: str) -> None:
        """Log debug message (only when DEBUG is True)"""
        if DEBUG and self.progress_callback:
            self.progress_callback(f"[DEBUG] {message}")

    def check_dependencies(self) -> Dict[str, bool]:
        """Check which extraction tools are available"""
        tools = {
            "binwalk": shutil.which("binwalk"),
            "unsquashfs": shutil.which("unsquashfs"),
            "sasquatch": shutil.which("sasquatch"),
            "jefferson": shutil.which("jefferson"),
            "ubireader_extract_images": shutil.which("ubireader_extract_images"),
            "cpio": shutil.which("cpio"),
            "gzip": shutil.which("gzip"),
            "lzma": shutil.which("lzma"),
            "xz": shutil.which("xz"),
        }

        self._tools = tools

        # Detect binwalk version
        if tools.get("binwalk"):
            self._detect_binwalk_version()

        return {k: v is not None for k, v in tools.items()}

    def _detect_binwalk_version(self) -> int:
        """Detect binwalk version (2.x vs 3.x have different CLIs)"""
        if self._binwalk_version:
            return self._binwalk_version

        try:
            result = subprocess.run(
                ["binwalk", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            version_str = result.stdout.strip()
            # binwalk 3.x outputs "binwalk 3.1.0"
            # binwalk 2.x outputs "Binwalk v2.3.4"
            if "3." in version_str:
                self._binwalk_version = 3
                self._log(f"[*] Detected binwalk v3.x")
            else:
                self._binwalk_version = 2
                self._log(f"[*] Detected binwalk v2.x")
        except Exception:
            self._binwalk_version = 2  # Default to v2 behavior

        return self._binwalk_version

    def get_missing_tools(self) -> List[str]:
        """Get list of recommended but missing tools"""
        if not self._tools:
            self.check_dependencies()

        critical = []
        if not self._tools.get("binwalk"):
            critical.append("binwalk")
        if not self._tools.get("unsquashfs") and not self._tools.get("sasquatch"):
            critical.append("sasquatch or squashfs-tools")

        return critical

    async def load_firmware(self, path: str) -> bool:
        """Load a firmware file for analysis"""
        firmware_path = Path(path).resolve()

        if not firmware_path.exists():
            self._log(f"[!] File not found: {firmware_path}")
            return False

        if not firmware_path.is_file():
            self._log(f"[!] Not a file: {firmware_path}")
            return False

        self.firmware_path = firmware_path
        self.output_dir = firmware_path.parent / f"{firmware_path.stem}_extracted"
        self.filesystems = []

        size = firmware_path.stat().st_size
        self._log(f"[+] Loaded: {firmware_path.name}")
        self._log(f"[*] Size: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")

        # Check file magic to identify type
        with open(firmware_path, 'rb') as f:
            magic = f.read(16)

        self._debug(f"File magic: {magic[:8].hex()}")

        # Check if this is already a raw filesystem image
        if magic[:4] in (b"hsqs", b"sqsh", b"shsq", b"qshs"):
            self._log("[*] File appears to be a raw SquashFS image")
            self._log("[*] Will extract directly without scanning")
            # Pre-populate filesystem list for direct extraction
            fs_size = self._find_squashfs_size(0)
            self.filesystems = [FilesystemEntry(
                offset=0,
                size=fs_size or size,
                fs_type=FilesystemType.SQUASHFS,
                description="Direct SquashFS image"
            )]
        elif magic[:2] == b"\x85\x19" or magic[:2] == b"\x19\x85":
            self._log("[*] File appears to be a raw JFFS2 image")
            self.filesystems = [FilesystemEntry(
                offset=0,
                size=size,
                fs_type=FilesystemType.JFFS2,
                description="Direct JFFS2 image"
            )]
        elif magic[:6] == b"070701":
            self._log("[*] File appears to be a CPIO archive")
            self.filesystems = [FilesystemEntry(
                offset=0,
                size=size,
                fs_type=FilesystemType.CPIO,
                description="Direct CPIO archive"
            )]

        return True

    async def scan(self) -> List[FilesystemEntry]:
        """Scan firmware for embedded filesystems using binwalk"""
        if not self.firmware_path:
            self._log("[!] No firmware loaded")
            return []

        self._debug(f"Firmware path: {self.firmware_path}")
        self._debug(f"File exists: {self.firmware_path.exists()}")
        self._debug(f"File size: {self.firmware_path.stat().st_size if self.firmware_path.exists() else 'N/A'}")

        if not self._tools.get("binwalk"):
            self._log("[!] binwalk not installed")
            self._log("[*] Install: brew install binwalk")
            return []

        # Detect binwalk version if not already done
        if not self._binwalk_version:
            self._detect_binwalk_version()

        self._log("[*] Scanning firmware with binwalk...")
        self._debug(f"Binwalk version: {self._binwalk_version}")

        try:
            # binwalk v2.x uses -B flag, v3.x doesn't need it
            if self._binwalk_version == 3:
                cmd = ["binwalk", str(self.firmware_path)]
            else:
                cmd = ["binwalk", "-B", str(self.firmware_path)]

            self._debug(f"Running command: {' '.join(cmd)}")

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
            )

            self._debug(f"binwalk return code: {result.returncode}")
            self._debug(f"binwalk stdout length: {len(result.stdout)}")
            self._debug(f"binwalk stderr length: {len(result.stderr)}")

            # Log raw output for debugging
            if result.stdout:
                self._debug("=== binwalk raw output ===")
                for line in result.stdout.strip().splitlines()[:30]:
                    self._debug(f"  {line}")
                if len(result.stdout.strip().splitlines()) > 30:
                    self._debug(f"  ... ({len(result.stdout.strip().splitlines())} total lines)")

            if result.stderr:
                for line in result.stderr.strip().splitlines():
                    if "error" in line.lower():
                        self._log(f"[!] {line}")
                    else:
                        self._debug(f"stderr: {line}")

            self.filesystems = self._parse_binwalk_output(result.stdout, self._binwalk_version)
            self._debug(f"Parsed {len(self.filesystems)} filesystem entries")

            if self.filesystems:
                self._log(f"[+] Found {len(self.filesystems)} filesystem(s):")
                for fs in self.filesystems:
                    size_str = f"{fs.size:,} bytes" if fs.size else "unknown size"
                    self._log(f"    0x{fs.offset:08X} [{fs.fs_type.value}] {size_str}")
            else:
                self._log("[!] No extractable filesystems found")
                # Also try direct signature detection as fallback
                direct_fs = await self._scan_direct_signatures()
                if direct_fs:
                    self.filesystems = direct_fs
                    self._log(f"[+] Direct scan found {len(direct_fs)} filesystem(s)")
                else:
                    self._log("[*] Try: binwalk <file> to see raw output")

            return self.filesystems

        except subprocess.TimeoutExpired:
            self._log("[!] Scan timeout (120s)")
            return []
        except Exception as e:
            self._log(f"[!] Scan failed: {e}")
            return []

    async def _scan_direct_signatures(self) -> List[FilesystemEntry]:
        """
        Directly scan file for filesystem magic bytes.
        Fallback when binwalk doesn't find anything.
        """
        entries = []

        try:
            with open(self.firmware_path, "rb") as f:
                data = f.read()

            # SquashFS signatures
            squashfs_magics = [b"hsqs", b"sqsh", b"shsq", b"qshs"]
            for magic in squashfs_magics:
                offset = 0
                while True:
                    pos = data.find(magic, offset)
                    if pos == -1:
                        break
                    size = self._find_squashfs_size(pos)
                    entries.append(FilesystemEntry(
                        offset=pos,
                        size=size,
                        fs_type=FilesystemType.SQUASHFS,
                        description=f"SquashFS at 0x{pos:X}"
                    ))
                    self._log(f"[+] Found SquashFS magic at 0x{pos:X}")
                    offset = pos + 4

            # JFFS2 signature - 0x1985 in little-endian
            # But be careful: this magic appears frequently, so validate it's at a clean offset
            jffs2_magic = b"\x85\x19"
            offset = 0
            while True:
                pos = data.find(jffs2_magic, offset)
                if pos == -1:
                    break
                # JFFS2 nodes are usually aligned to 4-byte boundaries
                # and the magic is followed by a node type (0x0001-0x0009)
                if pos + 4 < len(data):
                    node_type = data[pos + 2:pos + 4]
                    # Valid JFFS2 node types
                    if node_type in (b"\x00\x01", b"\x00\x02", b"\x00\x03",
                                     b"\x00\x04", b"\x00\x05", b"\x00\x06",
                                     b"\x00\x07", b"\x00\x08", b"\x00\x09",
                                     b"\x01\x00", b"\x02\x00", b"\x03\x00"):  # BE variants
                        entries.append(FilesystemEntry(
                            offset=pos,
                            size=None,
                            fs_type=FilesystemType.JFFS2,
                            description=f"JFFS2 at 0x{pos:X}"
                        ))
                        self._log(f"[+] Found JFFS2 magic at 0x{pos:X}")
                        break  # Only find first valid JFFS2
                offset = pos + 2

            # CPIO signature
            cpio_magic = b"070701"
            pos = data.find(cpio_magic)
            if pos != -1:
                entries.append(FilesystemEntry(
                    offset=pos,
                    size=None,
                    fs_type=FilesystemType.CPIO,
                    description=f"CPIO at 0x{pos:X}"
                ))
                self._log(f"[+] Found CPIO magic at 0x{pos:X}")

        except Exception as e:
            self._log(f"[!] Direct scan error: {e}")

        return entries

    def _parse_binwalk_output(self, output: str, version: int = 2) -> List[FilesystemEntry]:
        """
        Parse binwalk scan output to find filesystems.

        binwalk v2.x output format:
            DECIMAL       HEXADECIMAL     DESCRIPTION
            0             0x0             SquashFS filesystem...

        binwalk v3.x output format:
            0x00000000    65536   squashfs    SquashFS...
        """
        entries = []
        self._debug(f"Parsing binwalk output (version={version})")
        self._debug(f"Output has {len(output.strip().splitlines())} lines")

        for line in output.strip().splitlines():
            line_lower = line.lower()

            # Skip header lines
            if line.startswith("DECIMAL") or line.startswith("---") or not line.strip():
                self._debug(f"Skipping header/empty: {line[:60]}")
                continue

            # Detect filesystem type
            fs_type = None
            if "squashfs" in line_lower:
                fs_type = FilesystemType.SQUASHFS
            elif "jffs2" in line_lower:
                fs_type = FilesystemType.JFFS2
            elif "ubifs" in line_lower or "ubi image" in line_lower:
                fs_type = FilesystemType.UBIFS
            elif "cramfs" in line_lower:
                fs_type = FilesystemType.CRAMFS
            elif "cpio" in line_lower:
                fs_type = FilesystemType.CPIO
            elif any(x in line_lower for x in ["gzip", "lzma", "xz compressed", "xz data"]):
                fs_type = FilesystemType.COMPRESSED
            # Also check for raw filesystem/partition types
            elif "ext2" in line_lower or "ext3" in line_lower or "ext4" in line_lower:
                self._debug(f"Found EXT filesystem (not directly extractable): {line[:60]}")
            elif "fat" in line_lower or "vfat" in line_lower:
                self._debug(f"Found FAT filesystem: {line[:60]}")

            if fs_type:
                self._debug(f"Found {fs_type.value}: {line[:80]}")
                parts = line.split()
                offset = None
                size = None

                if version == 3:
                    # v3 format: 0x00000000    65536   squashfs    description
                    if parts and parts[0].startswith("0x"):
                        try:
                            offset = int(parts[0], 16)
                            # Second field might be size
                            if len(parts) > 1 and parts[1].isdigit():
                                size = int(parts[1])
                        except ValueError:
                            pass
                else:
                    # v2 format: decimal offset first
                    if parts and parts[0].isdigit():
                        offset = int(parts[0])

                # Try to extract size from description for both versions
                if size is None and "size:" in line_lower:
                    for j, part in enumerate(parts):
                        if part.lower() == "size:" and j + 1 < len(parts):
                            try:
                                size = int(parts[j + 1].replace(",", ""))
                            except ValueError:
                                pass

                if offset is not None:
                    entries.append(FilesystemEntry(
                        offset=offset,
                        size=size,
                        fs_type=fs_type,
                        description=line.strip()
                    ))

        return entries

    async def extract_all(self) -> ExtractionResult:
        """Extract all detected filesystems"""
        if not self.firmware_path:
            return ExtractionResult(
                success=False,
                firmware_path=Path("."),
                output_dir=Path("."),
                error="No firmware loaded"
            )

        if not self.filesystems:
            await self.scan()

        if not self.filesystems:
            return ExtractionResult(
                success=False,
                firmware_path=self.firmware_path,
                output_dir=self.output_dir or Path("."),
                error="No filesystems found"
            )

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._log(f"[*] Output: {self.output_dir}")
        self._log("")

        extracted = 0
        for fs in self.filesystems:
            self._log(f"{'=' * 50}")
            self._log(f"[*] Extracting {fs.fs_type.value} at 0x{fs.offset:X}")
            self._log(f"{'=' * 50}")

            success = await self._extract_filesystem(fs)
            if success:
                extracted += 1
                fs.extracted = True

        # Count total files extracted
        total_files = 0
        for item in self.output_dir.iterdir():
            if item.is_dir() and "root" in item.name:
                total_files += sum(1 for _ in item.rglob("*") if _.is_file())

        self._log("")
        self._log(f"{'=' * 50}")
        self._log(f"[+] EXTRACTION COMPLETE")
        self._log(f"{'=' * 50}")
        self._log(f"[+] Extracted: {extracted}/{len(self.filesystems)} filesystems")
        self._log(f"[+] Total files: {total_files}")

        return ExtractionResult(
            success=extracted > 0,
            firmware_path=self.firmware_path,
            output_dir=self.output_dir,
            filesystems=self.filesystems,
            extracted_count=extracted,
            total_files=total_files
        )

    async def _extract_filesystem(self, fs: FilesystemEntry) -> bool:
        """Extract a specific filesystem based on type"""
        self._debug(f"Extracting filesystem: type={fs.fs_type.value}, offset=0x{fs.offset:X}, size={fs.size}")

        handlers = {
            FilesystemType.SQUASHFS: self._extract_squashfs,
            FilesystemType.JFFS2: self._extract_jffs2,
            FilesystemType.UBIFS: self._extract_ubifs,
            FilesystemType.CPIO: self._extract_cpio,
            FilesystemType.COMPRESSED: self._extract_compressed,
        }

        handler = handlers.get(fs.fs_type)
        if handler:
            self._debug(f"Using handler: {handler.__name__}")
            result = await handler(fs)
            self._debug(f"Handler result: {result}")
            if fs.extract_path:
                self._debug(f"Extract path: {fs.extract_path}")
                if fs.extract_path.exists():
                    file_count = sum(1 for _ in fs.extract_path.rglob("*") if _.is_file())
                    dir_count = sum(1 for _ in fs.extract_path.rglob("*") if _.is_dir())
                    self._debug(f"Extracted: {file_count} files, {dir_count} directories")
            return result
        else:
            self._log(f"[!] No handler for {fs.fs_type.value}")
            return False

    def _find_squashfs_size(self, offset: int) -> Optional[int]:
        """Read squashfs superblock to get actual filesystem size"""
        try:
            with open(self.firmware_path, "rb") as f:
                f.seek(offset)
                magic = f.read(4)

                if magic not in (b"hsqs", b"sqsh", b"shsq", b"qshs"):
                    return None

                # SquashFS superblock: bytes_used at offset 40
                f.seek(offset + 40)
                if magic in (b"hsqs", b"shsq"):
                    # Little-endian
                    bytes_used = struct.unpack("<Q", f.read(8))[0]
                else:
                    # Big-endian
                    bytes_used = struct.unpack(">Q", f.read(8))[0]

                return bytes_used
        except Exception:
            return None

    def _carve_data(self, offset: int, size: int, dest_path: Path) -> bool:
        """Extract bytes from firmware at offset"""
        self._log(f"[*] Carving {size:,} bytes from 0x{offset:X}")
        try:
            with open(self.firmware_path, "rb") as src:
                src.seek(offset)
                data = src.read(size)
            with open(dest_path, "wb") as dst:
                dst.write(data)
            return len(data) == size
        except Exception as e:
            self._log(f"[!] Carve failed: {e}")
            return False

    async def _run_cmd(
        self,
        cmd: List[str],
        desc: str,
        cwd: Optional[Path] = None,
        timeout: int = 300,
        log_output: bool = True
    ) -> tuple[bool, str, str]:
        """Execute command asynchronously"""
        self._log(f"[*] {desc}")
        self._log(f"[*] Command: {' '.join(cmd)}")
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    cwd=str(cwd) if cwd else None,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
            )

            # Log output for debugging
            if log_output:
                if result.stdout.strip():
                    for line in result.stdout.strip().splitlines()[:10]:
                        self._log(f"    {line}")
                if result.stderr.strip():
                    for line in result.stderr.strip().splitlines()[:10]:
                        self._log(f"[!] {line}")

            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self._log(f"[!] Timeout after {timeout}s")
            return False, "", "timeout"
        except Exception as e:
            self._log(f"[!] Command failed: {e}")
            return False, "", str(e)

    async def _extract_squashfs(self, fs: FilesystemEntry) -> bool:
        """Extract SquashFS filesystem"""
        self._debug(f"Starting SquashFS extraction at offset 0x{fs.offset:X}")

        # Determine actual size from superblock
        actual_size = self._find_squashfs_size(fs.offset)
        if actual_size:
            self._log(f"[+] SquashFS size from superblock: {actual_size:,} bytes")
            size = actual_size
        elif fs.size:
            size = fs.size
            self._debug(f"Using provided size: {size:,} bytes")
        else:
            size = self.firmware_path.stat().st_size - fs.offset
            self._debug(f"Using remaining file size: {size:,} bytes")

        # Carve the squashfs image
        carved_path = self.output_dir / f"squashfs_0x{fs.offset:X}.img"
        self._debug(f"Carving to: {carved_path}")

        if not self._carve_data(fs.offset, size, carved_path):
            self._log("[!] Failed to carve SquashFS data")
            return False

        self._debug(f"Carved file size: {carved_path.stat().st_size:,} bytes")

        # Verify carved file has squashfs magic
        with open(carved_path, 'rb') as f:
            magic = f.read(4)
        self._debug(f"Carved file magic: {magic.hex()}")

        extract_dir = self.output_dir / f"squashfs-root_0x{fs.offset:X}"
        fs.extract_path = extract_dir

        # Try sasquatch first (handles vendor-modified squashfs)
        if self._tools.get("sasquatch"):
            self._debug("Trying sasquatch...")
            # Create extract dir first
            extract_dir.mkdir(parents=True, exist_ok=True)

            success, stdout, err = await self._run_cmd(
                ["sasquatch", "-f", "-d", str(extract_dir), str(carved_path)],
                "Extracting with sasquatch"
            )
            self._debug(f"sasquatch result: success={success}")
            if success or extract_dir.exists():
                file_count = len([f for f in extract_dir.rglob("*") if f.is_file()])
                dir_count = len([f for f in extract_dir.rglob("*") if f.is_dir()])
                self._debug(f"sasquatch extracted: {file_count} files, {dir_count} dirs")
                if file_count > 0:
                    self._log(f"[+] SquashFS extracted {file_count} files")
                    carved_path.unlink(missing_ok=True)
                    return True
                else:
                    self._debug("sasquatch succeeded but no files - trying unsquashfs")
            if err and "unknown" not in err.lower():
                self._debug(f"sasquatch stderr: {err[:200]}")

        # Fallback to standard unsquashfs
        if self._tools.get("unsquashfs"):
            self._debug("Trying unsquashfs...")
            # Clean up any partial extraction
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)

            success, stdout, err = await self._run_cmd(
                ["unsquashfs", "-f", "-d", str(extract_dir), str(carved_path)],
                "Extracting with unsquashfs"
            )
            self._debug(f"unsquashfs result: success={success}")
            if success or extract_dir.exists():
                file_count = len([f for f in extract_dir.rglob("*") if f.is_file()])
                dir_count = len([f for f in extract_dir.rglob("*") if f.is_dir()])
                self._debug(f"unsquashfs extracted: {file_count} files, {dir_count} dirs")
                if file_count > 0:
                    self._log(f"[+] SquashFS extracted {file_count} files")
                    carved_path.unlink(missing_ok=True)
                    return True
                else:
                    self._log("[!] unsquashfs succeeded but no files extracted")
            if err:
                self._debug(f"unsquashfs stderr: {err[:200]}")
                self._log(f"[!] unsquashfs error: {err[:100]}")

        # Keep carved file for manual inspection
        self._log(f"[!] Extraction failed - carved file kept at: {carved_path}")
        return False

    async def _extract_jffs2(self, fs: FilesystemEntry) -> bool:
        """Extract JFFS2 filesystem"""
        if not self._tools.get("jefferson"):
            self._log("[!] jefferson not installed")
            self._log("    Install: pip install jefferson")
            return False

        size = fs.size if fs.size else (self.firmware_path.stat().st_size - fs.offset)
        carved_path = self.output_dir / f"jffs2_0x{fs.offset:X}.img"
        self._carve_data(fs.offset, size, carved_path)

        extract_dir = self.output_dir / f"jffs2-root_0x{fs.offset:X}"
        extract_dir.mkdir(parents=True, exist_ok=True)
        fs.extract_path = extract_dir

        success, stdout, stderr = await self._run_cmd(
            ["jefferson", str(carved_path), "-d", str(extract_dir)],
            "Extracting JFFS2 with jefferson"
        )

        # Check if files were actually extracted
        extracted_files = list(extract_dir.rglob("*"))
        file_count = len([f for f in extracted_files if f.is_file()])

        if file_count > 0:
            self._log(f"[+] JFFS2 extracted {file_count} files")
            carved_path.unlink(missing_ok=True)
            return True
        else:
            self._log("[!] JFFS2 extraction produced no files")
            self._log("[*] This may not be a valid JFFS2 filesystem")
            # Keep the carved file for manual inspection
            return False

    async def _extract_ubifs(self, fs: FilesystemEntry) -> bool:
        """Extract UBIFS filesystem"""
        if not self._tools.get("ubireader_extract_images"):
            self._log("[!] ubireader not installed")
            self._log("    Install: pip install ubi_reader")
            return False

        size = fs.size if fs.size else (self.firmware_path.stat().st_size - fs.offset)
        carved_path = self.output_dir / f"ubifs_0x{fs.offset:X}.img"
        self._carve_data(fs.offset, size, carved_path)

        extract_dir = self.output_dir / f"ubifs-root_0x{fs.offset:X}"
        extract_dir.mkdir(exist_ok=True)
        fs.extract_path = extract_dir

        success, _, _ = await self._run_cmd(
            ["ubireader_extract_images", "-o", str(extract_dir), str(carved_path)],
            "Extracting UBIFS"
        )

        if success:
            carved_path.unlink(missing_ok=True)
        return success

    async def _extract_cpio(self, fs: FilesystemEntry) -> bool:
        """Extract CPIO archive"""
        if not self._tools.get("cpio"):
            self._log("[!] cpio not installed")
            return False

        size = fs.size if fs.size else (self.firmware_path.stat().st_size - fs.offset)
        carved_path = self.output_dir / f"cpio_0x{fs.offset:X}.cpio"
        self._carve_data(fs.offset, size, carved_path)

        extract_dir = self.output_dir / f"cpio-root_0x{fs.offset:X}"
        extract_dir.mkdir(exist_ok=True)
        fs.extract_path = extract_dir

        try:
            with open(carved_path, "rb") as f:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        ["cpio", "-idm", "--no-absolute-filenames"],
                        stdin=f,
                        cwd=str(extract_dir),
                        capture_output=True
                    )
                )
            return True
        except Exception as e:
            self._log(f"[!] CPIO extraction failed: {e}")
            return False

    async def _extract_compressed(self, fs: FilesystemEntry) -> bool:
        """Handle compressed data - decompress and scan for nested filesystems"""
        desc_lower = fs.description.lower()

        if "gzip" in desc_lower:
            ext, decompress_cmd = ".gz", ["gzip", "-d", "-k"]
        elif "lzma" in desc_lower:
            ext, decompress_cmd = ".lzma", ["lzma", "-d", "-k"]
        elif "xz" in desc_lower:
            ext, decompress_cmd = ".xz", ["xz", "-d", "-k"]
        else:
            return False

        if not self._tools.get(decompress_cmd[0]):
            self._log(f"[!] {decompress_cmd[0]} not installed")
            return False

        size = self.firmware_path.stat().st_size - fs.offset
        carved_path = self.output_dir / f"compressed_0x{fs.offset:X}{ext}"
        self._carve_data(fs.offset, size, carved_path)

        success, _, _ = await self._run_cmd(
            decompress_cmd + [str(carved_path)],
            f"Decompressing {ext} data"
        )

        if success:
            # Scan decompressed output for nested filesystems
            decompressed = carved_path.with_suffix("")
            if decompressed.exists():
                self._log("[*] Scanning decompressed data...")
                # Create sub-extractor for nested content
                sub_extractor = FirmwareExtractor(self.progress_callback)
                sub_extractor._tools = self._tools
                await sub_extractor.load_firmware(str(decompressed))
                nested = await sub_extractor.scan()

                for nested_fs in nested:
                    await sub_extractor._extract_filesystem(nested_fs)
                    if nested_fs.extract_path:
                        fs.extract_path = nested_fs.extract_path

        return True

    def get_extracted_roots(self) -> List[Path]:
        """Get paths to all extracted filesystem roots"""
        roots = []
        if self.output_dir and self.output_dir.exists():
            for item in self.output_dir.iterdir():
                if item.is_dir() and "root" in item.name:
                    roots.append(item)
        return sorted(roots)

    def list_files(self, root: Path, pattern: str = "*") -> List[Path]:
        """List files in extracted filesystem matching pattern"""
        if not root.exists():
            return []
        return sorted(root.rglob(pattern))
