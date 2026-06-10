# Windows Defender / Antivirus Problems

## Symptoms
- "Threat service has stopped" or Windows Security won't open.
- Real-time protection is off and won't turn on.
- Definition updates fail; scans error out.

## Common Root Causes
- A third-party antivirus disabling/blocking Defender.
- Corrupt Defender components or services.
- Group Policy/registry disabling Defender (sometimes set by malware).
- Corrupt definition cache or failed updates.

## Diagnostics / Event Log Signals
- Application log: Windows Defender (Microsoft-Windows-Windows Defender/Operational) error events.
- Services: "Microsoft Defender Antivirus Service" (WinDefend) not running.
- "This setting is managed by your administrator" on protection toggles.

## Recommended Fixes (require user confirmation)
1. If a third-party AV is installed, note that Defender real-time protection is intentionally off; ensure the third-party AV is healthy or uninstall it to restore Defender.
2. Update definitions: Windows Security > Virus & threat protection > Check for updates, or `MpCmdRun.exe -SignatureUpdate`.
3. Restart the service: `services.msc` > Microsoft Defender Antivirus Service (or `net stop WinDefend` is blocked by tamper protection - disable Tamper Protection first if needed).
4. Run `sfc /scannow` and `DISM /Online /Cleanup-Image /RestoreHealth` to repair components.
5. Re-register Defender via PowerShell if the app won't open (reset the Security app: Settings > Apps > Windows Security > Advanced options > Reset).
6. Scan for malware that may have disabled protection (use an offline scan).
7. Check Group Policy (`gpedit.msc`) and remove any policy disabling Defender (if unmanaged).

## Prevention
- Run only one real-time antivirus.
- Keep Tamper Protection on to block unauthorized changes.
