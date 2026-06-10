# Application Won't Install

## Symptoms
- Installer fails with errors like 0x80070005, 1603, 2502/2503, or "This app can't run on your PC".
- MSI installer rolls back at the end.
- "The installation package could not be opened" or digital signature errors.

## Common Root Causes
- Insufficient permissions (need admin) or corrupt Windows Installer service.
- Leftovers from a previous version blocking the install.
- Insufficient disk space; corrupt or incomplete download.
- Architecture mismatch (32-bit app on incompatible setup) or blocked by SmartScreen/policy.

## Diagnostics / Event Log Signals
- Application log: MsiInstaller events with the error code.
- Setup log from the installer (often in %TEMP%).
- Disk space low on the target drive.

## Recommended Fixes (require user confirmation)
1. Right-click the installer > Run as administrator; ensure you have admin rights.
2. Verify free disk space and re-download the installer (corrupt download is common); check the file hash if provided.
3. For errors 2502/2503, run the installer from an elevated Command Prompt, or fix permissions on %TEMP%.
4. Uninstall previous/partial versions; use the "Program Install and Uninstall" troubleshooter from Microsoft to clear stuck entries.
5. Restart the Windows Installer service: `services.msc` > Windows Installer; or `msiexec /unregister` then `msiexec /regserver`.
6. Temporarily disable SmartScreen/AV if it's blocking a trusted installer; re-enable afterward.
7. Run `sfc /scannow` if installs broadly fail.

## Prevention
- Download from official sources; keep disk space free.
- Fully uninstall old versions before reinstalling.
