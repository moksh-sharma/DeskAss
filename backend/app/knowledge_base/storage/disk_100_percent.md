# 100% Disk Usage

## Symptoms
- Task Manager shows disk at 100% constantly; PC very sluggish.
- Long delays opening apps/files; HDD light always on.
- High response times on the disk in Resource Monitor.

## Common Root Causes
- Windows Search indexing or SysMain (Superfetch) thrashing, especially on HDDs.
- Windows Update downloading/installing in the background.
- Antivirus full scan; telemetry (DiagTrack).
- Low RAM causing heavy paging to disk.
- A failing HDD with high latency.

## Diagnostics / Event Log Signals
- Task Manager > Processes sorted by Disk shows the top consumer.
- Resource Monitor > Disk shows high response time (ms) per file.
- System log: disk I/O retry events (Event ID 153) suggest failing hardware.

## Recommended Fixes (require user confirmation)
1. In Task Manager, sort by Disk and identify the top process (e.g. SearchHost, MsMpEng, Windows Update).
2. Let pending Windows Updates and antivirus scans finish; they often cause temporary 100% usage.
3. If SysMain/Superfetch thrashes an HDD, set "SysMain" service to Manual/Disabled (`services.msc`) and test.
4. Pause/rebuild the search index if SearchHost is the cause (Indexing Options > Rebuild).
5. Add RAM or close memory-heavy apps if paging is the cause (high RAM usage + high disk).
6. Check disk health/SMART; high response times with I/O retries suggest replacing a failing HDD (consider upgrading to SSD).
7. Run `chkdsk C: /f /r` for file system errors.

## Prevention
- Upgrade HDD to SSD for a major responsiveness gain.
- Keep enough RAM to avoid heavy paging.
