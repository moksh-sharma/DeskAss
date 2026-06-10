# Windows Won't Boot / Startup Failure

## Symptoms
- PC powers on but Windows does not load (black screen, spinning dots forever, or repeated restart loop).
- Errors: "Bootmgr is missing", "Operating System not found", "INACCESSIBLE_BOOT_DEVICE", "Automatic Repair couldn't repair your PC".
- Stuck on manufacturer logo or "Preparing Automatic Repair".

## Common Root Causes
- Corrupt boot configuration data (BCD) or master boot record.
- Failed or interrupted Windows Update.
- Disk disconnected, failing, or wrong boot order in BIOS/UEFI.
- Corrupt system files after an unexpected shutdown.
- Incompatible driver or recently changed hardware.

## Diagnostics / Event Log Signals
- Windows enters the Recovery Environment (WinRE) automatically after failed boots.
- Event log (once booted): unexpected shutdown (Kernel-Power 41), disk errors (Event ID 7, 51, 153).
- BIOS/UEFI shows the system drive missing or not first in boot order.

## Recommended Fixes (require user confirmation)
1. Boot to Windows Recovery: force-shutdown 3 times during boot to trigger WinRE, or boot from a Windows installation USB > Repair your computer.
2. Run Startup Repair: Troubleshoot > Advanced options > Startup Repair.
3. Rebuild boot files from Command Prompt: `bootrec /fixmbr`, `bootrec /fixboot`, `bootrec /scanos`, `bootrec /rebuildbcd`.
4. Run `chkdsk C: /f /r` and `sfc /scannow /offbootdir=C:\ /offwindir=C:\Windows`.
5. Verify the boot drive is detected and first in the BIOS/UEFI boot order; reseat the drive cable if a desktop.
6. Uninstall the latest quality/feature update: Advanced options > Uninstall Updates.
7. Use System Restore to a point before the issue began.
8. As a last resort, perform an in-place repair install (keeps files and apps).

## Prevention
- Don't power off during updates.
- Keep a recovery USB and recent backup.
- Enable System Restore points.
