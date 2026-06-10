# Windows Update Failing or Stuck

## Symptoms
- Updates fail with codes like 0x80070643, 0x800f0922, 0x80073712, 0x80240034, 0x8024401c.
- Update download stuck at 0% or a percentage; "Getting things ready" loops.
- "We couldn't complete the updates, undoing changes" after restart.

## Common Root Causes
- Corrupt Windows Update component store or cache.
- Insufficient free disk space (especially small system/EFI partition).
- Corrupt system files.
- Pending reboot or conflicting update.
- Third-party antivirus or VPN interfering with downloads.

## Diagnostics / Event Log Signals
- Setup and System logs show WindowsUpdateClient events (Event IDs 19, 20, 31, 25) with error codes.
- Low free space on C: or the recovery partition.
- CBS.log (C:\Windows\Logs\CBS) shows component store corruption.

## Recommended Fixes (require user confirmation)
1. Run the built-in troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Windows Update.
2. Free up disk space (need several GB); run Disk Cleanup including "Windows Update Cleanup".
3. Reset Update components: stop services `net stop wuauserv`, `net stop bits`, `net stop cryptsvc`, rename `C:\Windows\SoftwareDistribution` and `C:\Windows\System32\catroot2`, then restart the services.
4. Run `DISM /Online /Cleanup-Image /RestoreHealth` then `sfc /scannow`.
5. Temporarily disable third-party antivirus/VPN and retry.
6. Manually download the specific update (KB number) from the Microsoft Update Catalog and install it.
7. For feature update failures, use the Windows Update Assistant or Media Creation Tool for an in-place upgrade.

## Prevention
- Keep at least 20 GB free on C:.
- Restart regularly so pending updates complete.
- Avoid interrupting updates.
