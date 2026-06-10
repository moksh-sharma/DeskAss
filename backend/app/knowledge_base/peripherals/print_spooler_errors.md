# Print Spooler Crashing / Errors

## Symptoms
- "Print Spooler service is not running" error.
- Spooler stops immediately after starting.
- Can't add printers; print dialog hangs.

## Common Root Causes
- Corrupt stuck print jobs in the spool folder.
- Corrupt or conflicting printer drivers.
- Malware or a third-party print component crashing the service.
- Missing service dependencies.

## Diagnostics / Event Log Signals
- System/Application log: "The Print Spooler service terminated unexpectedly" (Service Control Manager Event ID 7034).
- PrintService operational log shows failing driver modules.

## Recommended Fixes (require user confirmation)
1. Stop the spooler: `services.msc` > Print Spooler > Stop (or `net stop spooler`).
2. Delete everything in `C:\Windows\System32\spool\PRINTERS` to clear stuck jobs.
3. Start the spooler again (`net start spooler`) and set Startup type to Automatic.
4. Confirm dependencies (RPC) are running.
5. Remove problematic printers/drivers: Print Management (`printmanagement.msc`) > remove old/duplicate drivers, then reinstall the correct one.
6. Run `sfc /scannow` if system files are suspected.
7. Scan for malware if the spooler repeatedly crashes.

## Prevention
- Keep only needed printer drivers installed.
- Update drivers from the manufacturer; remove unused printers.
