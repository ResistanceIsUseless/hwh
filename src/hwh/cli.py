"""
hwh CLI - Unified Hardware Hacking Tool

Command-line interface using Click.
"""

import sys
import json
from pathlib import Path
from typing import Optional

import click

from . import __version__
from .detect import detect, list_devices, print_detected_devices
from .backends import get_backend, SPIConfig, I2CConfig, GlitchConfig


# --------------------------------------------------------------------------
# CLI Group
# --------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.version_option(version=__version__)
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, verbose):
    """hwh - Hardware Hacking Toolkit

    A multi-device TUI for hardware security research.
    Supports Bus Pirate, Curious Bolt, Tigard, and more.

    Run without arguments to launch the TUI.
    """
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose

    # Launch TUI if no subcommand provided
    if ctx.invoked_subcommand is None:
        try:
            from .tui.app import run_tui
            run_tui()
        except ImportError as e:
            click.echo(f"Error: {e}", err=True)
            click.echo("Make sure textual is installed: pip install textual")
            ctx.exit(1)


# --------------------------------------------------------------------------
# Device Detection
# --------------------------------------------------------------------------

@cli.command()
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
@click.option('--all', 'show_all', is_flag=True, help='Include unknown devices')
def detect_cmd(as_json, show_all):
    """Detect connected hardware hacking tools."""
    devices = list_devices(include_unknown=show_all)
    
    if as_json:
        output = [
            {
                "name": d.name,
                "type": d.device_type,
                "port": d.port,
                "vid": f"{d.vid:04x}" if d.vid else None,
                "pid": f"{d.pid:04x}" if d.pid else None,
                "serial": d.serial,
                "capabilities": d.capabilities,
            }
            for d in devices
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        print_detected_devices()


# Aliases for convenience
cli.add_command(detect_cmd, name='detect')
cli.add_command(detect_cmd, name='devices')  # More intuitive alias


# --------------------------------------------------------------------------
# SPI Commands
# --------------------------------------------------------------------------

@cli.group()
def spi():
    """SPI flash operations."""
    pass


@spi.command('dump')
@click.option('-d', '--device', help='Device type (buspirate, tigard)')
@click.option('-o', '--output', type=click.Path(), required=True, help='Output file')
@click.option('-a', '--address', default='0x0', help='Start address (hex)')
@click.option('-s', '--size', default='0x100000', help='Size in bytes (hex)')
@click.option('--speed', default=1000000, help='SPI speed in Hz')
def spi_dump(device, output, address, size, speed):
    """Dump SPI flash to file."""
    # Parse hex values
    start_addr = int(address, 16) if address.startswith('0x') else int(address)
    dump_size = int(size, 16) if size.startswith('0x') else int(size)
    
    # Find suitable device
    devices = detect()
    
    if device:
        dev_info = devices.get(device)
    else:
        # Auto-select first SPI-capable device
        for key, dev in devices.items():
            if 'spi' in dev.capabilities:
                dev_info = dev
                click.echo(f"Auto-selected: {dev.name}")
                break
        else:
            click.echo("No SPI-capable device found", err=True)
            sys.exit(1)
    
    if not dev_info:
        click.echo(f"Device '{device}' not found", err=True)
        sys.exit(1)
    
    backend = get_backend(dev_info)
    if not backend:
        click.echo(f"No backend for {dev_info.device_type}", err=True)
        sys.exit(1)
    
    with backend:
        # Configure SPI
        config = SPIConfig(speed_hz=speed)
        if not backend.configure_spi(config):
            click.echo("SPI configuration failed", err=True)
            sys.exit(1)
        
        # Read flash ID first
        flash_id = backend.spi_flash_read_id()
        click.echo(f"Flash ID: {flash_id.hex()}")
        
        # Dump flash
        click.echo(f"Reading {dump_size} bytes from 0x{start_addr:06x}...")
        
        data = b''
        chunk_size = 4096
        
        with click.progressbar(length=dump_size, label='Dumping') as bar:
            while len(data) < dump_size:
                remaining = dump_size - len(data)
                chunk = min(chunk_size, remaining)
                
                chunk_data = backend.spi_flash_read(start_addr + len(data), chunk)
                if not chunk_data:
                    click.echo("\nRead error", err=True)
                    break
                
                data += chunk_data
                bar.update(len(chunk_data))
        
        # Write to file
        Path(output).write_bytes(data)
        click.echo(f"Written {len(data)} bytes to {output}")


@spi.command('id')
@click.option('-d', '--device', help='Device type')
def spi_id(device):
    """Read SPI flash JEDEC ID."""
    devices = detect()
    
    # Find device
    dev_info = None
    if device:
        dev_info = devices.get(device)
    else:
        for key, dev in devices.items():
            if 'spi' in dev.capabilities:
                dev_info = dev
                break
    
    if not dev_info:
        click.echo("No SPI device found", err=True)
        sys.exit(1)
    
    backend = get_backend(dev_info)
    with backend:
        backend.configure_spi(SPIConfig())
        flash_id = backend.spi_flash_read_id()
        
        if flash_id:
            click.echo(f"JEDEC ID: {flash_id.hex()}")
            # Decode common IDs
            if flash_id[0] == 0xEF:
                click.echo("  Manufacturer: Winbond")
            elif flash_id[0] == 0xC2:
                click.echo("  Manufacturer: Macronix")
            elif flash_id[0] == 0x20:
                click.echo("  Manufacturer: Micron")


# --------------------------------------------------------------------------
# I2C Commands
# --------------------------------------------------------------------------

@cli.group()
def i2c():
    """I2C operations."""
    pass


@i2c.command('scan')
@click.option('-d', '--device', help='Device type')
def i2c_scan(device):
    """Scan I2C bus for devices."""
    devices = detect()
    
    dev_info = None
    if device:
        dev_info = devices.get(device)
    else:
        for key, dev in devices.items():
            if 'i2c' in dev.capabilities:
                dev_info = dev
                break
    
    if not dev_info:
        click.echo("No I2C device found", err=True)
        sys.exit(1)
    
    backend = get_backend(dev_info)
    with backend:
        backend.configure_i2c(I2CConfig())
        
        found = backend.i2c_scan()
        
        if found:
            click.echo(f"Found {len(found)} device(s):")
            for addr in found:
                click.echo(f"  0x{addr:02x}")
        else:
            click.echo("No devices found")


# --------------------------------------------------------------------------
# Debug Commands
# --------------------------------------------------------------------------

@cli.group()
def debug():
    """Debug/SWD operations."""
    pass


@debug.command('dump')
@click.option('-d', '--device', help='Device type (stlink)')
@click.option('-o', '--output', type=click.Path(), required=True, help='Output file')
@click.option('-a', '--address', required=True, help='Start address (hex)')
@click.option('-s', '--size', required=True, help='Size in bytes (hex)')
@click.option('-t', '--target', default='auto', help='Target chip name')
def debug_dump(device, output, address, size, target):
    """Dump firmware via SWD/JTAG."""
    start_addr = int(address, 16) if address.startswith('0x') else int(address)
    dump_size = int(size, 16) if size.startswith('0x') else int(size)
    
    devices = detect()
    
    dev_info = None
    if device:
        dev_info = devices.get(device)
    else:
        for key, dev in devices.items():
            if 'swd' in dev.capabilities or 'debug' in dev.capabilities:
                dev_info = dev
                break
    
    if not dev_info:
        click.echo("No debug probe found", err=True)
        sys.exit(1)
    
    backend = get_backend(dev_info)
    with backend:
        if not backend.connect_target(target):
            click.echo("Target connection failed", err=True)
            sys.exit(1)
        
        backend.halt()
        
        click.echo(f"Dumping {dump_size} bytes from 0x{start_addr:08x}...")
        data = backend.dump_firmware(start_addr, dump_size)
        
        Path(output).write_bytes(data)
        click.echo(f"Written {len(data)} bytes to {output}")


@debug.command('regs')
@click.option('-d', '--device', help='Device type')
@click.option('-t', '--target', default='auto', help='Target chip')
def debug_regs(device, target):
    """Read CPU registers."""
    devices = detect()
    
    dev_info = None
    if device:
        dev_info = devices.get(device)
    else:
        for key, dev in devices.items():
            if 'debug' in dev.capabilities:
                dev_info = dev
                break
    
    if not dev_info:
        click.echo("No debug probe found", err=True)
        sys.exit(1)
    
    backend = get_backend(dev_info)
    with backend:
        backend.connect_target(target)
        backend.halt()
        
        regs = backend.read_registers()
        for name, value in regs.items():
            click.echo(f"  {name:6s}: 0x{value:08x}")


# --------------------------------------------------------------------------
# Glitch Commands
# --------------------------------------------------------------------------

@cli.group()
def glitch():
    """Voltage glitching operations."""
    pass


@glitch.command('single')
@click.option('-d', '--device', help='Device type (bolt, faultycat)')
@click.option('-w', '--width', type=float, default=350.0, help='Glitch width in nanoseconds')
@click.option('-o', '--offset', type=float, default=0.0, help='Trigger offset in nanoseconds')
def glitch_single(device, width, offset):
    """Trigger a single glitch."""
    devices = detect()

    # Find glitch-capable device
    if device:
        dev_info = devices.get(device)
    else:
        for key, dev in devices.items():
            if 'voltage_glitch' in dev.capabilities:
                dev_info = dev
                break
        else:
            click.echo("No glitching device found!", err=True)
            return 1

    if not dev_info:
        click.echo(f"Device '{device}' not found!", err=True)
        return 1

    backend = get_backend(dev_info)

    with backend:
        cfg = GlitchConfig(width_ns=width, offset_ns=offset)
        backend.configure_glitch(cfg)

        click.echo(f"Triggering glitch: {width:.0f}ns width, {offset:.0f}ns offset")
        backend.trigger()
        click.echo("✓ Glitch sent")


@glitch.command('sweep')
@click.option('-d', '--device', help='Device type (bolt, faultycat)')
@click.option('--width-min', type=float, default=50.0, help='Minimum glitch width (ns)')
@click.option('--width-max', type=float, default=1000.0, help='Maximum glitch width (ns)')
@click.option('--width-step', type=float, default=50.0, help='Width increment (ns)')
@click.option('--offset-min', type=float, default=0.0, help='Minimum offset (ns)')
@click.option('--offset-max', type=float, default=1000.0, help='Maximum offset (ns)')
@click.option('--offset-step', type=float, default=100.0, help='Offset increment (ns)')
@click.option('--delay', type=float, default=0.01, help='Delay between glitches (seconds)')
def glitch_sweep(device, width_min, width_max, width_step,
                 offset_min, offset_max, offset_step, delay):
    """Sweep glitch parameters."""
    import time

    devices = detect()

    # Find glitch-capable device
    if device:
        dev_info = devices.get(device)
    else:
        for key, dev in devices.items():
            if 'voltage_glitch' in dev.capabilities:
                dev_info = dev
                break
        else:
            click.echo("No glitching device found!", err=True)
            return 1

    backend = get_backend(dev_info)

    with backend:
        click.echo(f"Parameter sweep:")
        click.echo(f"  Width: {width_min}-{width_max}ns (step {width_step}ns)")
        click.echo(f"  Offset: {offset_min}-{offset_max}ns (step {offset_step}ns)")
        click.echo(f"  Delay: {delay}s between glitches")
        click.echo()

        width = width_min
        total = 0

        while width <= width_max:
            offset = offset_min

            while offset <= offset_max:
                cfg = GlitchConfig(width_ns=width, offset_ns=offset)
                backend.configure_glitch(cfg)
                backend.trigger()

                total += 1
                click.echo(f"[{total:4d}] width={width:5.0f}ns offset={offset:5.0f}ns", nl=False)
                click.echo('\r', nl=False)  # Overwrite same line

                time.sleep(delay)
                offset += offset_step

            width += width_step

        click.echo(f"\n✓ Sweep complete: {total} glitches sent")


@glitch.command('campaign')
@click.argument('config-file', type=click.Path(exists=True))
@click.option('-d', '--device', help='Device type (bolt, faultycat)')
def glitch_campaign(config_file, device):
    """Run automated glitching campaign from config file."""
    import asyncio
    from hwh.tui.campaign import run_campaign

    devices = detect()

    # Find glitch-capable device
    if device:
        dev_info = devices.get(device)
    else:
        for key, dev in devices.items():
            if 'voltage_glitch' in dev.capabilities:
                dev_info = dev
                break
        else:
            click.echo("No glitching device found!", err=True)
            return 1

    backend = get_backend(dev_info)

    click.echo(f"Running campaign from: {config_file}")
    click.echo()

    # Run campaign
    stats = asyncio.run(run_campaign(backend, config_file, log_callback=click.echo))

    # Display results
    click.echo()
    click.echo("Campaign complete!")
    click.echo(f"  Glitches sent: {stats.glitches_sent}")
    click.echo(f"  Elapsed time: {stats.elapsed_seconds:.1f}s")
    click.echo(f"  Rate: {stats.glitches_per_second:.1f} glitches/sec")

    if stats.success:
        click.echo("  Status: SUCCESS ✓")
    else:
        click.echo("  Status: No success detected")


# --------------------------------------------------------------------------
# TUI Interface
# --------------------------------------------------------------------------

@cli.command()
def tui():
    """Launch interactive TUI (Terminal User Interface)."""
    try:
        from .tui.app import run_tui
        run_tui()
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("Make sure textual is installed: pip install textual")
        return 1


# --------------------------------------------------------------------------
# Firmware Commands
# --------------------------------------------------------------------------

@cli.group()
def firmware():
    """Firmware extraction and analysis."""
    pass


@firmware.command('extract')
@click.argument('firmware_path', type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), help='Output directory (default: <firmware>_extracted)')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def firmware_extract(firmware_path, output, verbose):
    """Extract filesystems from firmware image.

    Supports: SquashFS, JFFS2, UBIFS, CPIO, TAR, ZIP, u-boot uImages

    Example:
        hwh firmware extract router.bin
        hwh firmware extract camera_fw.zip -o extracted/
    """
    import asyncio
    from .firmware.extractor import FirmwareExtractor

    def progress(msg):
        if verbose or not msg.startswith('[DEBUG]'):
            click.echo(msg)

    async def extract():
        extractor = FirmwareExtractor(progress_callback=progress)

        # Check dependencies
        deps = extractor.check_dependencies()
        missing = extractor.get_missing_tools()
        if missing:
            click.echo(f"Warning: Missing recommended tools: {', '.join(missing)}", err=True)
            click.echo("Install with: brew install binwalk sasquatch squashfs-tools", err=True)
            click.echo("              pip install jefferson ubi_reader", err=True)
            click.echo("")

        # Load firmware
        if not await extractor.load_firmware(firmware_path):
            click.echo("Failed to load firmware", err=True)
            return 1

        # Scan for filesystems
        filesystems = await extractor.scan()
        if not filesystems:
            click.echo("No extractable filesystems found", err=True)
            return 1

        # Extract all
        result = await extractor.extract_all()

        if result.success:
            click.echo("")
            click.echo("=" * 60)
            click.echo("EXTRACTION COMPLETE")
            click.echo("=" * 60)
            click.echo(f"Output directory: {result.output_dir}")
            click.echo(f"Extracted: {result.extracted_count}/{len(result.filesystems)} filesystems")

            # Show filesystem roots
            roots = extractor.get_extracted_roots()
            if roots:
                click.echo(f"\nFilesystem roots ({len(roots)}):")
                for root in roots:
                    file_count = sum(1 for _ in root.rglob('*') if _.is_file())
                    click.echo(f"  {root.name}/  ({file_count} files)")

            return 0
        else:
            click.echo(f"Extraction failed: {result.error}", err=True)
            return 1

    return asyncio.run(extract())


@firmware.command('analyze')
@click.argument('path', type=click.Path(exists=True))
@click.option('--creds-only', is_flag=True, help='Scan for credentials only')
@click.option('--export', type=click.Choice(['txt', 'json', 'csv', 'md']), help='Export format')
@click.option('-o', '--output', type=click.Path(), help='Export output file')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def firmware_analyze(path, creds_only, export, output, verbose):
    """Analyze extracted firmware for security issues.

    Scans for:
    - Hardcoded credentials (passwords, API keys)
    - Private keys and certificates
    - Unsafe functions in binaries
    - Configuration files with secrets

    Example:
        hwh firmware analyze router_extracted/
        hwh firmware analyze router_extracted/ --creds-only
        hwh firmware analyze router_extracted/ --export json -o findings.json
    """
    import asyncio
    from .firmware.analyzer import SecurityAnalyzer, Severity, AnalysisResult

    def progress(msg):
        if verbose or not msg.startswith('[DEBUG]'):
            click.echo(msg)

    async def analyze():
        analyzer = SecurityAnalyzer(progress_callback=progress)

        click.echo(f"Analyzing: {path}")
        click.echo("")

        # Run analysis
        if creds_only:
            # Just run credential scan
            await analyzer.find_credentials(Path(path))
            result = AnalysisResult(
                root_path=Path(path),
                findings=analyzer.findings,
                files_scanned=len(analyzer._scanned_files)
            )
        else:
            result = await analyzer.analyze_all(Path(path))

        if not result.findings:
            click.echo("No security findings.")
            return 0

        # Group by severity
        by_severity = {
            Severity.CRITICAL: [],
            Severity.HIGH: [],
            Severity.MEDIUM: [],
            Severity.LOW: [],
            Severity.INFO: []
        }

        for finding in result.findings:
            by_severity[finding.severity].append(finding)

        # Display results
        click.echo("=" * 60)
        click.echo("SECURITY FINDINGS")
        click.echo("=" * 60)
        click.echo(f"Total: {len(result.findings)} findings")
        click.echo("")

        for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            findings = by_severity[severity]
            if findings:
                color = {
                    Severity.CRITICAL: 'red',
                    Severity.HIGH: 'red',
                    Severity.MEDIUM: 'yellow',
                    Severity.LOW: 'yellow',
                    Severity.INFO: 'blue'
                }.get(severity, 'white')

                click.secho(f"\n{severity.value.upper()} ({len(findings)}):", fg=color, bold=True)
                for finding in findings[:10]:  # Show first 10
                    click.echo(f"  [{finding.category}] {finding.title}")
                    click.echo(f"    {finding.description}")
                    if finding.file_path:
                        click.echo(f"    File: {finding.file_path}")
                    if finding.line_number:
                        click.echo(f"    Line: {finding.line_number}")
                    if finding.matched_text:
                        text_preview = finding.matched_text[:80] + "..." if len(finding.matched_text) > 80 else finding.matched_text
                        click.echo(f"    Match: {text_preview}")

                if len(findings) > 10:
                    click.echo(f"  ... and {len(findings) - 10} more")

        # Show summary of detected items
        if analyzer.services or analyzer.software_packages or analyzer.custom_binaries:
            click.echo("")
            click.echo("=" * 60)
            click.echo("ANALYSIS SUMMARY")
            click.echo("=" * 60)

            if analyzer.services:
                click.echo(f"\nServices Detected: {len(analyzer.services)}")
                for service in analyzer.services[:10]:
                    status = "enabled" if service.enabled else "disabled"
                    click.echo(f"  [{service.type}] {service.name} ({status})")
                if len(analyzer.services) > 10:
                    click.echo(f"  ... and {len(analyzer.services) - 10} more")

            if analyzer.software_packages:
                click.echo(f"\nSoftware Packages: {len(analyzer.software_packages)}")
                for pkg in analyzer.software_packages[:15]:
                    click.echo(f"  {pkg.name} {pkg.version} (via {pkg.source})")
                if len(analyzer.software_packages) > 15:
                    click.echo(f"  ... and {len(analyzer.software_packages) - 15} more")

            if analyzer.custom_binaries:
                click.echo(f"\nCustom Binaries for Ghidra: {len(analyzer.custom_binaries)}")
                # Show interesting ones (those with interesting strings)
                interesting = [b for b in analyzer.custom_binaries if b.interesting_strings][:10]
                for binary in interesting:
                    click.echo(f"  {binary.path} ({binary.arch}, {binary.size:,} bytes)")
                    if binary.interesting_strings:
                        strings = ', '.join(binary.interesting_strings[:2])
                        click.echo(f"    Strings: {strings}")
                if len(interesting) > 10:
                    click.echo(f"  ... and {len(interesting) - 10} more interesting binaries")
                elif len(analyzer.custom_binaries) > len(interesting):
                    click.echo(f"  Plus {len(analyzer.custom_binaries) - len(interesting)} other binaries")

        # Export if requested
        if export and output:
            output_path = Path(output)
            if export == 'json':
                import json
                data = {
                    'firmware_path': str(path),
                    'total_findings': len(result.findings),
                    'by_severity': {s.value: len(by_severity[s]) for s in Severity},
                    'findings': [
                        {
                            'severity': f.severity.value,
                            'category': f.category,
                            'title': f.title,
                            'description': f.description,
                            'file_path': str(f.file_path) if f.file_path else None,
                            'line_number': f.line_number,
                            'matched_text': f.matched_text
                        }
                        for f in result.findings
                    ]
                }
                output_path.write_text(json.dumps(data, indent=2))
            elif export == 'csv':
                import csv
                with open(output_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Severity', 'Category', 'Title', 'Description', 'File', 'Line', 'Match'])
                    for finding in result.findings:
                        writer.writerow([
                            finding.severity.value,
                            finding.category,
                            finding.title,
                            finding.description,
                            str(finding.file_path) if finding.file_path else '',
                            finding.line_number or '',
                            finding.matched_text or ''
                        ])
            elif export == 'md':
                # Export markdown report
                firmware_name = Path(path).name
                success = analyzer.export_markdown_report(output_path, firmware_name)
                if not success:
                    click.echo("Failed to export markdown report", err=True)
                    return 1
            else:  # txt
                with open(output_path, 'w') as f:
                    f.write("FIRMWARE SECURITY ANALYSIS\n")
                    f.write("=" * 60 + "\n")
                    f.write(f"Firmware: {path}\n")
                    f.write(f"Total findings: {len(result.findings)}\n\n")

                    for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
                        findings = by_severity[severity]
                        if findings:
                            f.write(f"\n{severity.value} ({len(findings)})\n")
                            f.write("-" * 40 + "\n")
                            for finding in findings:
                                f.write(f"[{finding.category}] {finding.title}\n")
                                f.write(f"  {finding.description}\n")
                                if finding.file_path:
                                    f.write(f"  File: {finding.file_path}\n")
                                if finding.line_number:
                                    f.write(f"  Line: {finding.line_number}\n")
                                if finding.matched_text:
                                    f.write(f"  Match: {finding.matched_text}\n")
                                f.write("\n")

            click.echo(f"\nFindings exported to: {output_path}")

        return 0

    return asyncio.run(analyze())


@firmware.command('info')
@click.argument('firmware_path', type=click.Path(exists=True))
def firmware_info(firmware_path):
    """Show information about a firmware file.

    Example:
        hwh firmware info router.bin
    """
    import asyncio
    from .firmware.extractor import FirmwareExtractor

    async def show_info():
        extractor = FirmwareExtractor()

        if await extractor.load_firmware(firmware_path):
            filesystems = await extractor.scan()

            file_path = Path(firmware_path)
            size = file_path.stat().st_size

            click.echo(f"Firmware: {file_path.name}")
            click.echo(f"Size: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")

            # Check file type
            with open(file_path, 'rb') as f:
                magic = f.read(16).hex()
            click.echo(f"Magic: {magic[:32]}...")

            if filesystems:
                click.echo(f"\nFilesystems found: {len(filesystems)}")
                for fs in filesystems:
                    size_str = f"{fs.size:,} bytes" if fs.size else "unknown size"
                    click.echo(f"  0x{fs.offset:08X}  {fs.fs_type.value:12s}  {size_str}")
            else:
                click.echo("\nNo filesystems detected")
                click.echo("Try: binwalk <file> for manual inspection")

        return 0

    return asyncio.run(show_info())


@firmware.command('sbom')
@click.argument('path', type=click.Path(exists=True))
@click.option('-o', '--output', type=click.Path(), help='Output file (default: <name>.spdx.json)')
@click.option('--format', 'fmt', type=click.Choice(['json', 'tv']), default='json',
              help='Output format: json (SPDX JSON) or tv (Tag-Value)')
@click.option('--no-files', is_flag=True, help='Exclude file checksums (faster)')
@click.option('--max-files', type=int, default=500, help='Max files to include')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def firmware_sbom(path, output, fmt, no_files, max_files, verbose):
    """Generate Software Bill of Materials (SBOM) in SPDX format.

    Generates an SBOM from extracted firmware, including:
    - Detected software packages (opkg, dpkg)
    - File checksums (SHA256, SHA1, MD5)
    - CPE references for vulnerability correlation
    - Package URLs (PURL) for package managers

    Example:
        hwh firmware sbom ./router_extracted -o router.spdx.json
        hwh firmware sbom ./firmware_root --format tv -o router.spdx
        hwh firmware sbom ./extracted --no-files  # Skip file hashing
    """
    import asyncio
    from .firmware.analyzer import SecurityAnalyzer

    def progress(msg):
        if verbose:
            click.echo(msg)

    async def generate():
        path_obj = Path(path)

        if not path_obj.is_dir():
            click.echo(f"[!] Path must be a directory (extracted firmware root)")
            return 1

        # Determine output filename
        if output:
            output_path = Path(output)
        else:
            ext = '.spdx.json' if fmt == 'json' else '.spdx'
            output_path = path_obj.parent / f"{path_obj.name}{ext}"

        click.echo(f"[*] Generating SBOM for: {path}")
        click.echo(f"[*] Output: {output_path}")
        click.echo("")

        analyzer = SecurityAnalyzer(progress_callback=progress)

        # Generate SBOM
        sbom = await analyzer.generate_sbom(
            root_path=path_obj,
            firmware_name=path_obj.name,
            include_files=not no_files,
            max_files=max_files
        )

        # Export
        if fmt == 'json':
            success = sbom.export_spdx_json(output_path)
        else:
            success = sbom.export_spdx_tv(output_path)

        if success:
            click.echo("")
            click.echo(f"[+] SBOM GENERATED SUCCESSFULLY")
            click.echo(f"[+] Packages: {len(sbom.packages)}")
            click.echo(f"[+] Files: {len(sbom.files)}")
            click.echo(f"[+] Output: {output_path}")
            return 0
        else:
            click.echo(f"[!] Failed to write SBOM")
            return 1

    return asyncio.run(generate())


@firmware.command('hardening')
@click.argument('path', type=click.Path(exists=True))
@click.option('--export', type=click.Choice(['txt', 'json']), help='Export format')
@click.option('-o', '--output', type=click.Path(), help='Export output file')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def firmware_hardening(path, export, output, verbose):
    """Check binary security hardening (PIE, RELRO, NX, Canary).

    Analyzes ELF binaries in extracted firmware for security hardening:
    - PIE (Position Independent Executable) for ASLR
    - RELRO (Relocation Read-Only) for GOT protection
    - NX (No-Execute stack) to prevent shellcode
    - Stack Canary for buffer overflow protection
    - FORTIFY_SOURCE for runtime checks

    Example:
        hwh firmware hardening ./router_extracted
        hwh firmware hardening ./extracted --export json -o hardening.json
    """
    import asyncio
    import json
    from .firmware.analyzer import SecurityAnalyzer

    def progress(msg):
        if verbose:
            click.echo(msg)

    async def check_hardening():
        path_obj = Path(path)

        if not path_obj.is_dir():
            click.echo(f"[!] Path must be a directory (extracted firmware root)")
            return 1

        click.echo(f"[*] Checking binary hardening in: {path}")
        click.echo("")

        analyzer = SecurityAnalyzer(progress_callback=progress)
        findings = await analyzer.analyze_binary_hardening(path_obj)

        # Count by severity
        by_severity = {}
        for f in findings:
            sev = f.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

        click.echo("")
        click.echo("[+] BINARY HARDENING ANALYSIS COMPLETE")
        click.echo("")

        if findings:
            click.echo(f"Found {len(findings)} hardening issues:")
            for sev, count in sorted(by_severity.items()):
                click.echo(f"  {sev.upper()}: {count}")
            click.echo("")

            # Group by binary
            by_binary = {}
            for f in findings:
                binary = str(f.file_path)
                if binary not in by_binary:
                    by_binary[binary] = []
                by_binary[binary].append(f)

            click.echo("Issues by binary:")
            for binary, issues in sorted(by_binary.items()):
                click.echo(f"\n  {binary}:")
                for issue in issues:
                    click.echo(f"    - {issue.matched_text}")
        else:
            click.echo("No hardening issues found - binaries appear well-protected!")

        # Export if requested
        if export and output:
            output_path = Path(output)
            if export == 'json':
                data = {
                    'summary': by_severity,
                    'findings': [
                        {
                            'severity': f.severity.value,
                            'binary': str(f.file_path),
                            'issue': f.title,
                            'description': f.description,
                        }
                        for f in findings
                    ]
                }
                with open(output_path, 'w') as f:
                    json.dump(data, f, indent=2)
            else:
                with open(output_path, 'w') as f:
                    f.write("Binary Hardening Analysis Report\n")
                    f.write("=" * 40 + "\n\n")
                    for finding in findings:
                        f.write(f"[{finding.severity.value}] {finding.title}\n")
                        f.write(f"  File: {finding.file_path}\n")
                        f.write(f"  {finding.description}\n\n")

            click.echo(f"\n[+] Exported to: {output_path}")

        return 0

    return asyncio.run(check_hardening())


# --------------------------------------------------------------------------
# Interactive Shell
# --------------------------------------------------------------------------

@cli.command()
def shell():
    """Start interactive Python shell with hwh loaded."""
    try:
        from IPython import embed

        # Import useful things into namespace
        from . import detect, list_devices, get_backend
        from .backends import SPIConfig, I2CConfig, UARTConfig, GlitchConfig

        devices = detect()

        click.echo("hwh Interactive Shell")
        click.echo("=" * 40)
        click.echo("Available:")
        click.echo("  devices     - Dict of detected devices")
        click.echo("  detect()    - Refresh device list")
        click.echo("  get_backend(device) - Get backend for device")
        click.echo("")

        embed(colors='neutral')

    except ImportError:
        click.echo("IPython not installed. Install with: pip install ipython")
        click.echo("Falling back to basic Python shell...")

        import code
        code.interact(local=locals())


# --------------------------------------------------------------------------
# Entry Point
# --------------------------------------------------------------------------

def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
