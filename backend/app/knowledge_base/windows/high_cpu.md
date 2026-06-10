# High CPU Usage on Windows

## Symptoms
- CPU pinned at 90-100%, system unresponsive, loud fans.

## Common Root Causes
- A runaway process consuming CPU (browser tab, background updater).
- Windows Modules Installer / Windows Update running.
- Antivirus full scan (MsMpEng.exe / Antimalware Service Executable).
- Search indexer (SearchIndexer.exe) reindexing.
- Malware or cryptominer.
- Driver issues causing high System Interrupts.

## Diagnostics To Check
- Identify the top CPU process from Task Manager / diagnostics top_cpu_processes.
- Check if usage correlates with a specific app launch.
- Event Log: repeated application errors or service restarts.

## Recommended Fixes (require user confirmation)
1. Open Task Manager > Details, sort by CPU, identify the offender.
2. End or restart the offending process.
3. Pause antivirus scan or schedule it for off-hours.
4. Let Windows Update finish, then reboot.
5. Update or roll back recently changed device drivers.
6. Run a malware scan if an unknown process is consuming CPU.

## Prevention
- Schedule AV scans outside working hours.
- Keep drivers updated.
- Avoid excessive browser tabs/extensions.
