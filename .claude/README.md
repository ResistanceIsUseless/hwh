# Claude Code Documentation Directory

This directory contains specialized documentation and context for Claude Code AI assistants working on the hwh project.

## Files

### CLAUDE.md (Main Guide)
Primary documentation for Claude Code instances. Contains:
- Development commands (build, test, lint)
- Architecture overview (backends, TUI, protocols)
- Key bindings and UI patterns
- Critical notes about hardware specifics (Bus Pirate BPIO2, etc.)
- Code practices and configuration guidelines

### HARDWARE_SYNERGIES.md
Multi-device workflow documentation. Details:
- Synergy patterns (trigger + glitch, debug + monitor, etc.)
- Specific attack scenarios with device combinations
- Coordination mechanisms (GPIO triggers, USB software coordination)
- Device capability matrix
- Recommended device combinations by budget
- Implementation priorities for coordination features

**Use when**: Planning multi-device features, implementing coordination modes, designing glitch campaigns

### MISSING_FEATURES.md
Comprehensive feature gap analysis. Documents:
- Missing features per device (Bus Pirate, Bolt, Tigard, ST-Link, etc.)
- Implementation completeness percentages
- Shared infrastructure needs (protocol decoders, flash database, parsers)
- Priority recommendations
- Feature dependencies

**Use when**: Planning new features, prioritizing development work, implementing device backends

### hwh-development.md
Legacy development skill guide (may be outdated). Contains:
- Backend implementation patterns
- TUI panel patterns
- Protocol references (SPI flash, I2C, JTAG)
- Mock backend for testing
- Dependencies and references

**Note**: Some information may be superseded by CLAUDE.md. Use as supplementary reference.

### textual-tui.md
Textual framework patterns and best practices. Covers:
- Worker patterns for hardware I/O
- Custom widget implementations (HexViewer, StatusIndicator)
- TCSS styling guidelines
- Message passing patterns
- Real-time data display
- Error handling patterns
- Performance tips

**Use when**: Implementing TUI features, creating custom widgets, debugging UI issues

### settings.local.json
Claude Code permissions configuration. Contains pre-approved bash command patterns for this project.

## Usage by Claude Code Agents

These files are automatically provided to Claude Code as context. For specialized tasks:

1. **Hardware integration work**: Reference HARDWARE_SYNERGIES.md for multi-device patterns
2. **Feature planning**: Check MISSING_FEATURES.md for gaps and priorities
3. **UI development**: Use textual-tui.md for Textual framework patterns
4. **General development**: CLAUDE.md is always relevant

## Maintenance

When updating these files:
- Keep CLAUDE.md as the authoritative main guide
- Update MISSING_FEATURES.md as features are implemented
- Add new synergy patterns to HARDWARE_SYNERGIES.md as they're discovered
- Keep textual-tui.md synchronized with app.py key bindings and patterns
