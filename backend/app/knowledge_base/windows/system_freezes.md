# System Freezes / Not Responding

## Symptoms
- Entire PC locks up; mouse won't move or moves but nothing responds.
- Apps show "Not Responding"; only a hard reset recovers it.
- Freezes on wake from sleep or after a period of use.

## Common Root Causes
- Driver deadlocks (GPU, storage, chipset).
- Failing disk causing I/O stalls.
- RAM exhaustion / heavy paging.
- Overheating throttling to a halt.
- Corrupt system files or a problematic background service.

## Diagnostics / Event Log Signals
- System log: "The system has rebooted without cleanly shutting down" if force-reset (Kernel-Power 41).
- Disk events (Event ID 51, 153, 7) indicating I/O errors.
- Ntfs or storahci warnings; high disk active time near 100%.

## Recommended Fixes (require user confirmation)
1. Check RAM and disk usage in Task Manager when responsive; identify processes pinning resources.
2. Update GPU, chipset, and storage (AHCI/NVMe) drivers; roll back if a recent driver caused it.
3. Run `chkdsk C: /f /r` and review disk SMART health.
4. Run `sfc /scannow` and `DISM /Online /Cleanup-Image /RestoreHealth`.
5. Disable fast startup (Control Panel > Power Options > Choose what the power buttons do) if freezes occur on wake.
6. Perform a clean boot (msconfig > Services: hide Microsoft, disable rest) to isolate a background app/service.
7. Test memory with `mdsched.exe`.

## Prevention
- Keep drivers current; avoid beta drivers on work machines.
- Maintain free RAM and disk headroom.
- Replace aging disks proactively.
