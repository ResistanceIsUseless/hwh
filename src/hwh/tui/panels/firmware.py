"""
Firmware Analysis Panel

TUI panel for extracting, navigating, and analyzing firmware images
for security vulnerabilities.

Features:
- Firmware extraction (SquashFS, JFFS2, UBIFS, CPIO)
- File system navigation with tree view
- Pattern searching (credentials, strings)
- Binary analysis for unsafe functions
- Security findings with severity levels
"""

import asyncio
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import (
    Static, Button, Input, Log, TabbedContent, TabPane,
    Tree, DirectoryTree, DataTable, ProgressBar
)
from textual.widgets.tree import TreeNode
from textual.messages import Message
from textual.screen import ModalScreen

from ...firmware.extractor import FirmwareExtractor, FilesystemEntry, ExtractionResult
from ...firmware.analyzer import SecurityAnalyzer, Finding, Severity, AnalysisResult


class FilePickerScreen(ModalScreen[Optional[Path]]):
    """Modal screen for picking a firmware file"""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, start_path: Optional[Path] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_path = start_path or Path.home()
        self.selected_path: Optional[Path] = None

    def compose(self) -> ComposeResult:
        with Container(id="file-picker-modal"):
            yield Static("Select Firmware File", id="picker-title")

            # Current path display
            yield Static(str(self.start_path), id="current-path")

            # Directory tree
            yield DirectoryTree(str(self.start_path), id="file-picker-tree")

            # Selected file display
            yield Static("No file selected", id="selected-file")

            # Buttons
            with Horizontal(id="picker-buttons"):
                yield Button("Open", id="btn-picker-open", variant="primary")
                yield Button("Cancel", id="btn-picker-cancel")

    def on_mount(self) -> None:
        tree = self.query_one("#file-picker-tree", DirectoryTree)
        tree.show_root = True
        tree.show_guides = True

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection in tree"""
        self.selected_path = Path(event.path)
        try:
            selected_label = self.query_one("#selected-file", Static)
            size = self.selected_path.stat().st_size
            size_str = self._format_size(size)
            selected_label.update(f"Selected: {self.selected_path.name} ({size_str})")
        except Exception:
            pass

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Update current path display when directory is expanded"""
        try:
            path_label = self.query_one("#current-path", Static)
            path_label.update(str(event.path))
        except Exception:
            pass

    def _format_size(self, size: int) -> str:
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024:.1f}MB"
        else:
            return f"{size / 1024 / 1024 / 1024:.1f}GB"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-picker-open":
            if self.selected_path and self.selected_path.is_file():
                self.dismiss(self.selected_path)
            else:
                self.app.notify("Please select a file", severity="warning")
        elif event.button.id == "btn-picker-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class FirmwareLoadedMessage(Message):
    """Message sent when firmware is loaded"""
    def __init__(self, path: Path):
        super().__init__()
        self.path = path


class FirmwarePanel(Container):
    """
    Firmware analysis panel.

    Unlike device panels, this doesn't require a physical device.
    It operates on firmware files loaded from disk.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # State
        self.firmware_path: Optional[Path] = None
        self.extracted_roots: List[Path] = []
        self.current_root: Optional[Path] = None

        # Analysis engines
        self.extractor = FirmwareExtractor(progress_callback=self._log_output)
        self.analyzer = SecurityAnalyzer(progress_callback=self._log_output)

        # Findings
        self.findings: List[Finding] = []

        # Current file preview
        self.preview_path: Optional[Path] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="firmware-panel"):
            # Header with load controls
            with Horizontal(classes="firmware-header"):
                yield Static("Firmware Analysis", classes="firmware-title")
                yield Input(
                    placeholder="Path to firmware file...",
                    id="firmware-path-input",
                    classes="firmware-path-input"
                )
                yield Button("Load", id="btn-load-firmware", classes="btn-small")
                yield Button("Open...", id="btn-browse", classes="btn-small")

            # Status bar with progress indicator
            with Horizontal(classes="firmware-status-bar"):
                yield Static("No firmware loaded", id="firmware-status", classes="firmware-status")
                yield Static("", id="firmware-action", classes="firmware-action")
                yield ProgressBar(id="firmware-progress", classes="firmware-progress", show_eta=False)
                yield Static("", id="firmware-tools-status", classes="firmware-tools-status")

            # Main tabbed content
            with TabbedContent(id="firmware-tabs"):
                # Extract tab
                with TabPane("Extract", id="tab-extract"):
                    yield from self._build_extract_tab()

                # Browse tab
                with TabPane("Browse", id="tab-browse"):
                    yield from self._build_browse_tab()

                # Search tab
                with TabPane("Search", id="tab-search"):
                    yield from self._build_search_tab()

                # Findings tab
                with TabPane("Findings", id="tab-findings"):
                    yield from self._build_findings_tab()

            # Console/output area
            with Container(classes="firmware-console") as console:
                console.border_title = "output"
                yield Log(id="firmware-log", classes="firmware-log")

                with Horizontal(classes="input-row"):
                    yield Static("$>", classes="input-prompt")
                    yield Input(
                        placeholder="command...",
                        id="firmware-input",
                        classes="firmware-input"
                    )

    def _build_extract_tab(self) -> ComposeResult:
        """Build the extraction tab"""
        with Vertical(classes="extract-content"):
            yield Static("Firmware Extraction", classes="section-title")
            yield Static(
                "Load a firmware file, scan for filesystems, and extract them.",
                classes="help-text"
            )

            # Extraction controls
            with Horizontal(classes="button-row"):
                yield Button("Open Firmware...", id="btn-open-extract", classes="btn-action")
                yield Button("Scan", id="btn-scan", classes="btn-action")
                yield Button("Extract All", id="btn-extract-all", classes="btn-action")
                yield Button("Check Tools", id="btn-check-tools", classes="btn-action")

            # Filesystem list
            with Container(classes="fs-list-container") as fs_list:
                fs_list.border_title = "detected filesystems"
                yield ScrollableContainer(id="fs-list")

            # Extraction results
            with Container(classes="extract-results") as results:
                results.border_title = "extracted roots"
                yield ScrollableContainer(id="extract-results-list")

    def _build_browse_tab(self) -> ComposeResult:
        """Build the file browser tab"""
        with Horizontal(classes="browse-content"):
            # File tree on the left
            with Vertical(classes="browse-tree-section"):
                yield Static("File System", classes="section-title")

                # Action buttons row
                with Horizontal(classes="quick-nav"):
                    yield Button("Open Firmware...", id="btn-open-browse", classes="btn-action")

                # Quick nav buttons for extracted filesystem
                with Horizontal(classes="quick-nav"):
                    yield Button("/etc", id="nav-etc", classes="btn-nav")
                    yield Button("/bin", id="nav-bin", classes="btn-nav")
                    yield Button("/var", id="nav-var", classes="btn-nav")
                    yield Button("/root", id="nav-root", classes="btn-nav")

                # Tree placeholder (will be populated when filesystem is extracted)
                with ScrollableContainer(id="file-tree-container", classes="file-tree-container"):
                    yield Static("Open and extract a firmware file to browse", id="tree-placeholder", classes="placeholder")

            # File preview on the right
            with Vertical(classes="browse-preview-section"):
                yield Static("File Preview", classes="section-title")
                with Horizontal(classes="preview-controls"):
                    yield Button("Text", id="btn-view-text", classes="btn-small")
                    yield Button("Hex", id="btn-view-hex", classes="btn-small")
                    yield Button("Strings", id="btn-view-strings", classes="btn-small")
                    yield Button("Info", id="btn-view-info", classes="btn-small")

                with Container(classes="preview-container") as preview:
                    preview.border_title = "preview"
                    yield Log(id="file-preview", classes="file-preview-log")

    def _build_search_tab(self) -> ComposeResult:
        """Build the search tab"""
        with Vertical(classes="search-content"):
            yield Static("Security Search", classes="section-title")
            yield Static(
                "Search extracted filesystem for security issues.",
                classes="help-text"
            )

            # Quick scans
            with Horizontal(classes="button-row"):
                yield Button("Credentials", id="btn-scan-creds", classes="btn-action")
                yield Button("Configs", id="btn-scan-configs", classes="btn-action")
                yield Button("Binaries", id="btn-scan-binaries", classes="btn-action")
                yield Button("Full Scan", id="btn-scan-full", classes="btn-action")

            # Custom search
            with Horizontal(classes="search-row"):
                yield Input(
                    placeholder="Regex pattern to search...",
                    id="search-pattern",
                    classes="search-input"
                )
                yield Button("Search", id="btn-search", classes="btn-action")

            # Search results
            with Container(classes="search-results") as results:
                results.border_title = "search results"
                yield Log(id="search-results-log", classes="search-results-log")

    def _build_findings_tab(self) -> ComposeResult:
        """Build the findings tab"""
        with Vertical(classes="findings-content"):
            # Summary header
            with Horizontal(classes="findings-summary"):
                yield Static("0", id="count-critical", classes="count-critical")
                yield Static("Critical", classes="label-count")
                yield Static("0", id="count-high", classes="count-high")
                yield Static("High", classes="label-count")
                yield Static("0", id="count-medium", classes="count-medium")
                yield Static("Medium", classes="label-count")
                yield Static("0", id="count-low", classes="count-low")
                yield Static("Low", classes="label-count")

            # Export controls
            with Horizontal(classes="button-row"):
                yield Button("Export TXT", id="btn-export-txt", classes="btn-action")
                yield Button("Export JSON", id="btn-export-json", classes="btn-action")
                yield Button("Export CSV", id="btn-export-csv", classes="btn-action")
                yield Button("Clear", id="btn-clear-findings", classes="btn-action")

            # Findings table
            with Container(classes="findings-table-container"):
                table = DataTable(id="findings-table", classes="findings-table")
                table.add_columns("Sev", "Category", "Title", "Location")
                yield table

    def _log_output(self, text: str) -> None:
        """Write to the output log"""
        try:
            log = self.query_one("#firmware-log", Log)
            log.write_line(text)
        except Exception:
            pass

    def _update_status(self, text: str) -> None:
        """Update the status bar"""
        try:
            status = self.query_one("#firmware-status", Static)
            status.update(text)
        except Exception:
            pass

    def _update_action(self, text: str) -> None:
        """Update the action indicator (what's currently happening)"""
        try:
            action = self.query_one("#firmware-action", Static)
            action.update(text)
        except Exception:
            pass

    def _update_tools_status(self, text: str) -> None:
        """Update the tools status indicator"""
        try:
            tools_status = self.query_one("#firmware-tools-status", Static)
            tools_status.update(text)
        except Exception:
            pass

    def _show_progress(self, show: bool = True, total: int = 100) -> None:
        """Show or hide the progress bar"""
        try:
            progress = self.query_one("#firmware-progress", ProgressBar)
            if show:
                progress.update(total=total, progress=0)
                progress.display = True
            else:
                progress.display = False
        except Exception:
            pass

    def _update_progress(self, value: int) -> None:
        """Update progress bar value"""
        try:
            progress = self.query_one("#firmware-progress", ProgressBar)
            progress.update(progress=value)
        except Exception:
            pass

    def _check_and_show_tools(self) -> bool:
        """Check tools and show status, returns True if critical tools available"""
        tools = self.extractor.check_dependencies()
        missing = self.extractor.get_missing_tools()

        if missing:
            self._update_tools_status(f"[!] Missing: {', '.join(missing)}")
            self._log_output(f"[!] Missing tools: {', '.join(missing)}")
            self._log_output("[*] Run 'Check Tools' for details")
            return False
        else:
            self._update_tools_status("[OK] Tools ready")
            return True

    async def _open_file_picker(self) -> None:
        """Open file picker dialog to select firmware"""
        # Start from home directory or last used path
        start_path = Path.home()
        if self.firmware_path:
            start_path = self.firmware_path.parent

        def handle_file_selected(selected: Optional[Path]) -> None:
            if selected:
                # Update the path input field
                try:
                    path_input = self.query_one("#firmware-path-input", Input)
                    path_input.value = str(selected)
                except Exception:
                    pass
                # Load the firmware
                asyncio.create_task(self.load_firmware(str(selected)))

        await self.app.push_screen(
            FilePickerScreen(start_path=start_path),
            handle_file_selected
        )

    async def load_firmware(self, path: str) -> bool:
        """Load a firmware file"""
        self._update_action("Loading...")
        success = await self.extractor.load_firmware(path)
        if success:
            self.firmware_path = self.extractor.firmware_path
            self._update_status(f"Loaded: {self.firmware_path.name}")
            self._log_output(f"[+] Firmware loaded: {self.firmware_path}")

            # Check tools after loading
            self._check_and_show_tools()

            # Prompt next step
            self._update_action("Ready - Click 'Scan' to find filesystems")
            self._log_output("[*] Next: Click 'Scan' on Extract tab or type 'scan'")
        else:
            self._update_action("Load failed")
            self._update_status("Load failed")
        return success

    async def scan_firmware(self) -> List[FilesystemEntry]:
        """Scan loaded firmware for filesystems"""
        if not self.firmware_path:
            self._log_output("[!] No firmware loaded")
            self._update_action("No firmware - Load a file first")
            return []

        # Check for binwalk
        if not self.extractor._tools.get("binwalk"):
            self.extractor.check_dependencies()
        if not self.extractor._tools.get("binwalk"):
            self._log_output("[!] binwalk not installed - cannot scan")
            self._log_output("[*] Install: brew install binwalk")
            self._update_action("Missing binwalk!")
            self._update_tools_status("[!] Missing: binwalk")
            return []

        self._update_action("Scanning...")
        self._show_progress(True)
        self._update_progress(30)

        filesystems = await self.extractor.scan()

        self._update_progress(100)
        self._show_progress(False)

        await self._update_filesystem_list(filesystems)

        if filesystems:
            self._update_action(f"Found {len(filesystems)} filesystem(s) - Click 'Extract All'")
            self._log_output(f"[*] Next: Click 'Extract All' or type 'extract'")
        else:
            self._update_action("No filesystems found")

        return filesystems

    async def extract_firmware(self) -> ExtractionResult:
        """Extract all filesystems from firmware"""
        if not self.firmware_path:
            self._log_output("[!] No firmware loaded")
            self._update_action("No firmware - Load a file first")
            return ExtractionResult(
                success=False,
                firmware_path=Path("."),
                output_dir=Path("."),
                error="No firmware loaded"
            )

        # Check tools before extraction
        if not self.extractor._tools:
            self.extractor.check_dependencies()

        missing = self.extractor.get_missing_tools()
        if missing:
            self._update_tools_status(f"[!] Missing: {', '.join(missing)}")
            self._log_output(f"[!] Missing required tools: {', '.join(missing)}")
            self._log_output("[*] Extraction may fail - install missing tools first")

        self._update_action("Extracting...")
        self._show_progress(True)
        self._update_progress(10)

        result = await self.extractor.extract_all()

        self._update_progress(100)
        self._show_progress(False)

        if result.success:
            self.extracted_roots = self.extractor.get_extracted_roots()
            if self.extracted_roots:
                self.current_root = self.extracted_roots[0]
                await self._update_extracted_roots()
                await self._build_file_tree()
                self._update_action(f"Extracted {result.extracted_count} filesystem(s), {result.total_files} files")
                self._update_status(f"Extracted: {self.firmware_path.name}")
                self._log_output("[*] Next: Browse files or run security scans")
        else:
            self._update_action(f"Extraction failed: {result.error or 'unknown error'}")
            if "unsquashfs" in str(result.error).lower() or "sasquatch" in str(result.error).lower():
                self._log_output("[!] SquashFS extraction failed - try: brew install sasquatch")
            elif "jefferson" in str(result.error).lower():
                self._log_output("[!] JFFS2 extraction failed - try: pip install jefferson")

        return result

    async def _update_filesystem_list(self, filesystems: List[FilesystemEntry]) -> None:
        """Update the filesystem list display"""
        try:
            fs_list = self.query_one("#fs-list", ScrollableContainer)
            await fs_list.remove_children()

            if not filesystems:
                await fs_list.mount(
                    Static("No filesystems found", classes="placeholder")
                )
                return

            for i, fs in enumerate(filesystems):
                size_str = f"{fs.size:,}" if fs.size else "?"
                with Horizontal(classes="fs-entry") as entry:
                    await fs_list.mount(entry)
                    await entry.mount(Static(f"0x{fs.offset:08X}", classes="fs-offset"))
                    await entry.mount(Static(fs.fs_type.value, classes="fs-type"))
                    await entry.mount(Static(f"{size_str} bytes", classes="fs-size"))
                    await entry.mount(Button(
                        "Extract",
                        id=f"extract-{i}",
                        classes="btn-small"
                    ))
        except Exception as e:
            self._log_output(f"[!] Error updating list: {e}")

    async def _update_extracted_roots(self) -> None:
        """Update the extracted roots display"""
        try:
            results_list = self.query_one("#extract-results-list", ScrollableContainer)
            await results_list.remove_children()

            if not self.extracted_roots:
                await results_list.mount(
                    Static("No extracted filesystems", classes="placeholder")
                )
                return

            for root in self.extracted_roots:
                file_count = sum(1 for _ in root.rglob("*") if _.is_file())
                with Horizontal(classes="root-entry") as entry:
                    await results_list.mount(entry)
                    await entry.mount(Static(root.name, classes="root-name"))
                    await entry.mount(Static(f"({file_count} files)", classes="root-count"))
                    await entry.mount(Button(
                        "Browse",
                        id=f"browse-{root.name}",
                        classes="btn-small"
                    ))
        except Exception as e:
            self._log_output(f"[!] Error updating roots: {e}")

    async def _build_file_tree(self) -> None:
        """Build the file tree for the current root"""
        if not self.current_root:
            return

        try:
            container = self.query_one("#file-tree-container", ScrollableContainer)
            await container.remove_children()

            # Create a simple tree widget
            tree = Tree(self.current_root.name, id="file-tree")
            tree.root.expand()

            # Add files/directories (limited depth for performance)
            await self._populate_tree_node(tree.root, self.current_root, max_depth=3)

            await container.mount(tree)
        except Exception as e:
            self._log_output(f"[!] Error building tree: {e}")

    async def _populate_tree_node(
        self,
        node: TreeNode,
        path: Path,
        max_depth: int,
        current_depth: int = 0
    ) -> None:
        """Recursively populate tree nodes"""
        if current_depth >= max_depth:
            return

        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

            for item in items[:100]:  # Limit items per directory
                if item.is_dir():
                    child = node.add(f"[dir]{item.name}/", data=item)
                    if current_depth < max_depth - 1:
                        await self._populate_tree_node(child, item, max_depth, current_depth + 1)
                else:
                    size = item.stat().st_size
                    size_str = self._format_size(size)
                    node.add(f"{item.name} ({size_str})", data=item)
        except PermissionError:
            pass
        except Exception:
            pass

    def _format_size(self, size: int) -> str:
        """Format file size for display"""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}K"
        elif size < 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024:.1f}M"
        else:
            return f"{size / 1024 / 1024 / 1024:.1f}G"

    async def preview_file(self, path: Path, mode: str = "text") -> None:
        """Preview a file in the preview pane"""
        self.preview_path = path

        try:
            preview = self.query_one("#file-preview", Log)
            preview.clear()

            if not path.exists():
                preview.write_line(f"File not found: {path}")
                return

            size = path.stat().st_size
            preview.write_line(f"File: {path.name}")
            preview.write_line(f"Size: {self._format_size(size)}")
            preview.write_line("-" * 40)

            if mode == "text":
                await self._preview_text(path, preview)
            elif mode == "hex":
                await self._preview_hex(path, preview)
            elif mode == "strings":
                await self._preview_strings(path, preview)
            elif mode == "info":
                await self._preview_info(path, preview)

        except Exception as e:
            self._log_output(f"[!] Preview error: {e}")

    async def _preview_text(self, path: Path, preview: Log) -> None:
        """Preview file as text"""
        try:
            content = path.read_text(errors="ignore")
            lines = content.splitlines()[:200]  # Limit lines
            for line in lines:
                preview.write_line(line[:200])  # Limit line length
            if len(content.splitlines()) > 200:
                preview.write_line(f"... ({len(content.splitlines())} total lines)")
        except Exception as e:
            preview.write_line(f"Error reading file: {e}")

    async def _preview_hex(self, path: Path, preview: Log) -> None:
        """Preview file as hex dump"""
        try:
            with open(path, "rb") as f:
                data = f.read(1024)  # First 1KB

            offset = 0
            for i in range(0, len(data), 16):
                chunk = data[i:i + 16]
                hex_part = " ".join(f"{b:02x}" for b in chunk)
                ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
                preview.write_line(f"{offset:08x}  {hex_part:<48}  {ascii_part}")
                offset += 16

            if path.stat().st_size > 1024:
                preview.write_line(f"... (showing first 1KB of {self._format_size(path.stat().st_size)})")
        except Exception as e:
            preview.write_line(f"Error reading file: {e}")

    async def _preview_strings(self, path: Path, preview: Log) -> None:
        """Extract and preview strings from file"""
        try:
            strings = await self.analyzer.extract_strings(path)
            for s in strings[:100]:
                preview.write_line(s[:200])
            if len(strings) > 100:
                preview.write_line(f"... ({len(strings)} total strings)")
        except Exception as e:
            preview.write_line(f"Error extracting strings: {e}")

    async def _preview_info(self, path: Path, preview: Log) -> None:
        """Preview file metadata/info"""
        try:
            stat_info = path.stat()
            preview.write_line(f"Path: {path}")
            preview.write_line(f"Size: {stat_info.st_size} bytes")
            preview.write_line(f"Mode: {oct(stat_info.st_mode)}")

            # Check file type
            with open(path, "rb") as f:
                magic = f.read(16)

            if magic[:4] == b"\x7fELF":
                preview.write_line("Type: ELF Binary")
                # Could add more ELF parsing here
            elif magic[:2] == b"#!":
                shebang = magic.split(b"\n")[0].decode("utf-8", errors="ignore")
                preview.write_line(f"Type: Script ({shebang})")
            elif magic[:4] == b"hsqs" or magic[:4] == b"sqsh":
                preview.write_line("Type: SquashFS")
            else:
                preview.write_line(f"Magic: {magic[:8].hex()}")
        except Exception as e:
            preview.write_line(f"Error getting info: {e}")

    async def run_security_scan(self, scan_type: str = "full") -> AnalysisResult:
        """Run security analysis on extracted filesystem"""
        if not self.current_root:
            self._log_output("[!] No extracted filesystem to analyze")
            return AnalysisResult(root_path=Path("."))

        if scan_type == "full":
            result = await self.analyzer.analyze_all(self.current_root)
        elif scan_type == "credentials":
            self.analyzer.findings = []
            await self.analyzer.find_credentials(self.current_root)
            result = AnalysisResult(
                root_path=self.current_root,
                findings=self.analyzer.findings
            )
        elif scan_type == "configs":
            self.analyzer.findings = []
            await self.analyzer.analyze_configs(self.current_root)
            result = AnalysisResult(
                root_path=self.current_root,
                findings=self.analyzer.findings
            )
        elif scan_type == "binaries":
            self.analyzer.findings = []
            await self.analyzer.analyze_binaries(self.current_root)
            result = AnalysisResult(
                root_path=self.current_root,
                findings=self.analyzer.findings
            )
        else:
            result = await self.analyzer.analyze_all(self.current_root)

        self.findings = result.findings
        await self._update_findings_display()

        return result

    async def search_pattern(self, pattern: str) -> List[Finding]:
        """Search for custom pattern in filesystem"""
        if not self.current_root:
            self._log_output("[!] No extracted filesystem to search")
            return []

        findings = await self.analyzer.search_pattern(self.current_root, pattern)

        # Add to findings and update display
        self.findings.extend(findings)
        await self._update_findings_display()

        # Also show in search results
        try:
            results_log = self.query_one("#search-results-log", Log)
            results_log.clear()
            for f in findings:
                results_log.write_line(str(f))
        except Exception:
            pass

        return findings

    async def _update_findings_display(self) -> None:
        """Update the findings tab display"""
        try:
            # Update counts
            self.query_one("#count-critical", Static).update(
                str(sum(1 for f in self.findings if f.severity == Severity.CRITICAL))
            )
            self.query_one("#count-high", Static).update(
                str(sum(1 for f in self.findings if f.severity == Severity.HIGH))
            )
            self.query_one("#count-medium", Static).update(
                str(sum(1 for f in self.findings if f.severity == Severity.MEDIUM))
            )
            self.query_one("#count-low", Static).update(
                str(sum(1 for f in self.findings if f.severity == Severity.LOW))
            )

            # Update table
            table = self.query_one("#findings-table", DataTable)
            table.clear()

            for finding in self.findings:
                sev_display = {
                    Severity.CRITICAL: "[CRIT]",
                    Severity.HIGH: "[HIGH]",
                    Severity.MEDIUM: "[MED]",
                    Severity.LOW: "[LOW]",
                    Severity.INFO: "[INFO]",
                }.get(finding.severity, "[?]")

                location = ""
                if finding.file_path:
                    location = str(finding.file_path)
                    if finding.line_number:
                        location += f":{finding.line_number}"

                table.add_row(
                    sev_display,
                    finding.category,
                    finding.title[:40],
                    location[:40]
                )
        except Exception as e:
            self._log_output(f"[!] Error updating findings: {e}")

    async def export_findings(self, format: str = "txt") -> bool:
        """Export findings to file"""
        if not self.findings:
            self._log_output("[!] No findings to export")
            return False

        output_dir = self.extractor.output_dir or Path(".")
        output_path = output_dir / f"findings.{format}"

        success = self.analyzer.export_findings(output_path, format)
        if success:
            self._log_output(f"[+] Exported to: {output_path}")
        return success

    async def send_command(self, command: str) -> None:
        """Handle command input"""
        self._log_output(f"$ {command}")

        parts = command.strip().split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == "help":
            self._show_help()
        elif cmd == "load":
            if len(parts) > 1:
                await self.load_firmware(" ".join(parts[1:]))
            else:
                self._log_output("[!] Usage: load <path>")
        elif cmd == "scan":
            await self.scan_firmware()
        elif cmd == "extract":
            await self.extract_firmware()
        elif cmd == "creds":
            await self.run_security_scan("credentials")
        elif cmd == "configs":
            await self.run_security_scan("configs")
        elif cmd == "binaries":
            await self.run_security_scan("binaries")
        elif cmd == "analyze":
            await self.run_security_scan("full")
        elif cmd == "search":
            if len(parts) > 1:
                await self.search_pattern(" ".join(parts[1:]))
            else:
                self._log_output("[!] Usage: search <pattern>")
        elif cmd == "export":
            format = parts[1] if len(parts) > 1 else "txt"
            await self.export_findings(format)
        elif cmd == "strings":
            if len(parts) > 1 and self.current_root:
                path = self.current_root / parts[1].lstrip("/")
                if path.exists():
                    strings = await self.analyzer.extract_strings(path)
                    for s in strings[:50]:
                        self._log_output(s)
                else:
                    self._log_output(f"[!] File not found: {parts[1]}")
            else:
                self._log_output("[!] Usage: strings <path>")
        elif cmd == "ls":
            if self.current_root:
                path = self.current_root
                if len(parts) > 1:
                    path = path / parts[1].lstrip("/")
                if path.exists():
                    for item in sorted(path.iterdir())[:50]:
                        prefix = "d " if item.is_dir() else "- "
                        self._log_output(f"{prefix}{item.name}")
                else:
                    self._log_output(f"[!] Not found: {path}")
            else:
                self._log_output("[!] No filesystem extracted")
        elif cmd == "cat":
            if len(parts) > 1 and self.current_root:
                path = self.current_root / parts[1].lstrip("/")
                if path.exists() and path.is_file():
                    try:
                        content = path.read_text(errors="ignore")
                        for line in content.splitlines()[:100]:
                            self._log_output(line)
                    except Exception as e:
                        self._log_output(f"[!] Error: {e}")
                else:
                    self._log_output(f"[!] File not found: {parts[1]}")
            else:
                self._log_output("[!] Usage: cat <path>")
        else:
            self._log_output(f"[!] Unknown command: {cmd}")
            self._log_output("[*] Type 'help' for available commands")

    def _show_help(self) -> None:
        """Display help"""
        help_text = """
Firmware Analysis Commands:
  help                - Show this help
  load <path>         - Load firmware file
  scan                - Scan for filesystems
  extract             - Extract all filesystems

Security Analysis:
  analyze             - Run full security scan
  creds               - Scan for credentials
  configs             - Analyze config files
  binaries            - Check binaries for unsafe functions
  search <pattern>    - Search with regex pattern

File Operations:
  ls [path]           - List directory contents
  cat <path>          - Display file contents
  strings <path>      - Extract strings from file

Export:
  export [txt|json|csv] - Export findings
"""
        self._log_output(help_text)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        if not button_id:
            return

        if button_id == "btn-load-firmware":
            try:
                path_input = self.query_one("#firmware-path-input", Input)
                if path_input.value:
                    await self.load_firmware(path_input.value)
            except Exception:
                pass

        elif button_id in ("btn-browse", "btn-open-extract", "btn-open-browse"):
            await self._open_file_picker()

        elif button_id == "btn-scan":
            await self.scan_firmware()

        elif button_id == "btn-extract-all":
            await self.extract_firmware()

        elif button_id == "btn-check-tools":
            tools = self.extractor.check_dependencies()
            self._log_output("[*] Available tools:")
            for tool, available in tools.items():
                status = "[+]" if available else "[-]"
                self._log_output(f"  {status} {tool}")

        elif button_id == "btn-scan-creds":
            await self.run_security_scan("credentials")

        elif button_id == "btn-scan-configs":
            await self.run_security_scan("configs")

        elif button_id == "btn-scan-binaries":
            await self.run_security_scan("binaries")

        elif button_id == "btn-scan-full":
            await self.run_security_scan("full")

        elif button_id == "btn-search":
            try:
                pattern_input = self.query_one("#search-pattern", Input)
                if pattern_input.value:
                    await self.search_pattern(pattern_input.value)
            except Exception:
                pass

        elif button_id == "btn-export-txt":
            await self.export_findings("txt")

        elif button_id == "btn-export-json":
            await self.export_findings("json")

        elif button_id == "btn-export-csv":
            await self.export_findings("csv")

        elif button_id == "btn-clear-findings":
            self.findings = []
            await self._update_findings_display()

        elif button_id == "btn-view-text" and self.preview_path:
            await self.preview_file(self.preview_path, "text")

        elif button_id == "btn-view-hex" and self.preview_path:
            await self.preview_file(self.preview_path, "hex")

        elif button_id == "btn-view-strings" and self.preview_path:
            await self.preview_file(self.preview_path, "strings")

        elif button_id == "btn-view-info" and self.preview_path:
            await self.preview_file(self.preview_path, "info")

        # Quick nav buttons
        elif button_id.startswith("nav-") and self.current_root:
            dir_name = button_id.replace("nav-", "")
            path = self.current_root / dir_name
            if path.exists():
                # Could expand tree to this location
                self._log_output(f"[*] Navigate to /{dir_name}")

        # Browse extracted root
        elif button_id.startswith("browse-"):
            root_name = button_id.replace("browse-", "")
            for root in self.extracted_roots:
                if root.name == root_name:
                    self.current_root = root
                    await self._build_file_tree()
                    self._log_output(f"[*] Browsing: {root.name}")
                    break

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle file tree selection"""
        node = event.node
        if node.data and isinstance(node.data, Path):
            path = node.data
            if path.is_file():
                await self.preview_file(path, "text")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission"""
        if event.input.id == "firmware-input":
            command = event.value.strip()
            if command:
                event.input.value = ""
                await self.send_command(command)

        elif event.input.id == "firmware-path-input":
            path = event.value.strip()
            if path:
                await self.load_firmware(path)

        elif event.input.id == "search-pattern":
            pattern = event.value.strip()
            if pattern:
                await self.search_pattern(pattern)
