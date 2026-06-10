# Microsoft Teams Freezing or Crashing

## Symptoms
- Teams freezes during meetings or screen sharing.
- High CPU/RAM while Teams is running.
- Teams becomes unresponsive and must be force-closed.

## Common Root Causes
- Corrupt Teams cache.
- Insufficient RAM during video meetings.
- Outdated Teams client or GPU drivers.
- Hardware acceleration conflicts.

## Diagnostics / Event Log Signals
- Application Hang events for Teams.exe / ms-teams.exe.
- High memory usage by Teams in top_memory_processes.

## Recommended Fixes (require user confirmation)
1. Clear the Teams cache: quit Teams, delete %AppData%\Microsoft\Teams (classic) or reset the new Teams app.
2. Update Teams to the latest version.
3. Disable GPU hardware acceleration in Teams settings.
4. Close other memory-heavy apps before meetings.
5. Update graphics drivers.
6. Reinstall Teams if crashes persist.

## Prevention
- Keep Teams and GPU drivers updated.
- Ensure adequate RAM (8GB+ free for video calls).
