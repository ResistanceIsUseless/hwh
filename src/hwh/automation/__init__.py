"""
Automation Module - Automated security testing and analysis tools.

Provides automated workflows for:
- UART baud rate detection and command fuzzing
- Smart glitch parameter search with learning
- Logic analyzer triggered glitching
- Protocol capture, replay, and fuzzing
- Firmware extraction and secret scanning

Example - UART Baud Scanner:
    >>> from hwh.automation import UARTScanner, scan_uart_baud
    >>> report = await scan_uart_baud(port="/dev/ttyUSB0")
    >>> print(f"Detected: {report.best_baud} baud")

Example - Smart Glitch Campaign:
    >>> from hwh.automation import SmartGlitchCampaign
    >>> campaign = SmartGlitchCampaign(
    ...     glitch_backend=bolt,
    ...     monitor_backend=buspirate,
    ...     width_range=(50, 500),
    ...     offset_range=(0, 10000)
    ... )
    >>> campaign.classifier.add_success_pattern("flag{")
    >>> stats = await campaign.run(strategy="adaptive", max_attempts=1000)

Example - LA Triggered Glitch:
    >>> from hwh.automation import LATriggeredGlitcher, TriggerPattern
    >>> glitcher = LATriggeredGlitcher(la_backend=bolt, glitch_backend=bolt)
    >>> patterns = await glitcher.learn_patterns(
    ...     pattern_type=TriggerPattern.IDLE_HIGH,
    ...     channel=0,
    ...     min_duration_us=1000
    ... )
    >>> glitcher.configure(pattern=TriggerPattern.IDLE_HIGH, glitch_delay_us=500)
    >>> await glitcher.arm_and_wait()

Example - Protocol Replay:
    >>> from hwh.automation import ProtocolCapture, ProtocolReplay, Protocol
    >>> capture = ProtocolCapture(backend=buspirate, protocol=Protocol.SPI)
    >>> session = await capture.start(duration=5.0)
    >>> session.save("boot_traffic.json")
    >>> # Later: modify and replay
    >>> session = CaptureSession.load("boot_traffic.json")
    >>> replay = ProtocolReplay(backend=buspirate)
    >>> await replay.play(session)

Example - Firmware Analysis:
    >>> from hwh.automation import FirmwareAnalyzer, analyze_firmware
    >>> report = await analyze_firmware("router_firmware.bin")
    >>> print(report.summary())
    >>> report.save("analysis.json")

Example - Glitch Calibration:
    >>> from hwh.automation import GlitchCalibrator, calibrate_setup
    >>> # Measure latency with loopback (glitch output -> LA input)
    >>> profile = await calibrate_setup(
    ...     glitch_backend=bolt,
    ...     la_backend=bolt,
    ...     profile_name="my_bolt_10cm_wire",
    ...     channel=0,  # LA channel connected to glitch output
    ...     iterations=100
    ... )
    >>> print(f"Latency: {profile.trigger_latency_ns:.0f}ns")
    >>> print(f"Jitter: {profile.trigger_jitter}")
    >>>
    >>> # Load and apply to shared config
    >>> from hwh.automation import PortableGlitchConfig, CalibrationManager
    >>> config = PortableGlitchConfig.load("stm32_rdp_bypass.json")
    >>> manager = CalibrationManager()
    >>> width, offset = manager.apply_calibration(config, "my_bolt_10cm_wire")
"""

from .uart_scanner import (
    UARTScanner,
    UARTCommandScanner,
    UARTScanReport,
    BaudScanResult,
    ScanResult,
    scan_uart_baud,
    COMMON_BAUD_RATES,
    EXTENDED_BAUD_RATES,
    COMMON_COMMANDS,
)

from .smart_glitch import (
    SmartGlitchCampaign,
    GlitchResult,
    GlitchAttempt,
    CampaignStats,
    ResultClassifier,
    ParameterRegion,
)

from .la_glitch import (
    LATriggeredGlitcher,
    SignalAnalyzer,
    TriggerPattern,
    PatternMatch,
    LAGlitchConfig,
)

from .protocol_replay import (
    Protocol,
    Transaction,
    CaptureSession,
    ProtocolCapture,
    ProtocolReplay,
    ProtocolFuzzer,
)

from .firmware_analysis import (
    FirmwareAnalyzer,
    AnalysisReport,
    Finding,
    FindingType,
    analyze_firmware,
)

from .calibration import (
    GlitchCalibrator,
    CalibrationProfile,
    CalibrationManager,
    PortableGlitchConfig,
    LatencyMeasurement,
    JitterStats,
    calibrate_setup,
)

__all__ = [
    # UART Scanner
    "UARTScanner",
    "UARTCommandScanner",
    "UARTScanReport",
    "BaudScanResult",
    "ScanResult",
    "scan_uart_baud",
    "COMMON_BAUD_RATES",
    "EXTENDED_BAUD_RATES",
    "COMMON_COMMANDS",

    # Smart Glitch
    "SmartGlitchCampaign",
    "GlitchResult",
    "GlitchAttempt",
    "CampaignStats",
    "ResultClassifier",
    "ParameterRegion",

    # LA Triggered Glitch
    "LATriggeredGlitcher",
    "SignalAnalyzer",
    "TriggerPattern",
    "PatternMatch",
    "LAGlitchConfig",

    # Protocol Replay
    "Protocol",
    "Transaction",
    "CaptureSession",
    "ProtocolCapture",
    "ProtocolReplay",
    "ProtocolFuzzer",

    # Firmware Analysis
    "FirmwareAnalyzer",
    "AnalysisReport",
    "Finding",
    "FindingType",
    "analyze_firmware",

    # Calibration
    "GlitchCalibrator",
    "CalibrationProfile",
    "CalibrationManager",
    "PortableGlitchConfig",
    "LatencyMeasurement",
    "JitterStats",
    "calibrate_setup",
]
