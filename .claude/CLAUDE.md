
## Git Workflow
- **Always use feature branches** for new work (e.g., `feature/bp-status-tab`)
- **Commit frequently** - small, incremental commits that can be rolled back
- **Never use `git checkout HEAD --`** to restore files - this destroys uncommitted work
- Use `git stash` before switching branches or making risky changes

## Bus Pirate Development
- **Always use BPIO2 FlatBuffers library** (bundled in `src/hwh/pybpio/`)
- The BPIO2 library connects via the binary CDC interface (buspirate3), NOT the terminal interface
- Test connection with `BPIOClient` before adding UI features
- Reference working test scripts in `scripts/` directory
