
## Git Workflow
- **Always use feature branches** for new work (e.g., `feature/bp-status-tab`)
- **Commit frequently** - small, incremental commits that can be rolled back
- **Never use `git checkout HEAD --`** to restore files - this destroys uncommitted work
- Use `git stash` before switching branches or making risky changes

## Bus Pirate 5/6 Development (BPIO2 Only)
- **Only support Bus Pirate 5 and Bus Pirate 6** - older versions (v3, v4) are NOT supported
- **Always use BPIO2 FlatBuffers library** (bundled in `src/hwh/pybpio/`)
- The BPIO2 library connects via the binary CDC interface (buspirate3), NOT the terminal interface
- BPIO2 Documentation: https://docs.buspirate.com/docs/binmode-reference/protocol-bpio2/
- Test connection with `BPIOClient` before adding UI features
- Reference working test scripts in `scripts/` directory
- **UART BPIO2 not implemented in firmware** - use terminal fallback for UART mode
