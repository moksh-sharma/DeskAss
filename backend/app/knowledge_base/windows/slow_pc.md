# Windows PC Running Slow

## Symptoms
- General sluggishness, apps take a long time to open.
- Performance degrades after the machine has been on for hours.
- Fan running constantly, system feels hot.

## Common Root Causes
- Too many startup programs increasing boot and idle load.
- High background CPU usage (Windows Update, antivirus scan, search indexer).
- Low available RAM causing heavy disk paging.
- Disk nearly full (<10% free) slowing the OS.
- Fragmented or failing HDD, or an SSD that is full.
- Memory leak in a long-running app (e.g. browser with many tabs, Outlook).

## Diagnostics To Check
- CPU usage > 80% sustained -> identify top process in Task Manager.
- RAM usage > 85% with low available memory -> memory pressure.
- Disk usage > 90% -> free up space.
- Top CPU/RAM consumers: chrome.exe, Teams.exe, outlook.exe, antimalware service.

## Recommended Fixes (require user confirmation)
1. Open Task Manager (Ctrl+Shift+Esc) and end unresponsive high-usage processes.
2. Disable unnecessary startup apps: Task Manager > Startup tab > Disable.
3. Run Disk Cleanup and clear temporary files (%TEMP%).
4. Restart the machine to clear memory leaks if uptime is high.
5. Ensure at least 15% free disk space.
6. Check Windows Update is not mid-installation.

## Prevention
- Keep at least 20% free disk space.
- Limit startup applications.
- Restart the PC at least once a week.
- Keep drivers and Windows updated.
