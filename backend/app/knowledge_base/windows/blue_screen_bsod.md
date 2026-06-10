# Blue Screen of Death (BSOD) / Stop Errors

## Symptoms
- PC suddenly shows a blue screen with a sad face and a stop code, then restarts.
- Repeated crashes with codes like CRITICAL_PROCESS_DIED, IRQL_NOT_LESS_OR_EQUAL, PAGE_FAULT_IN_NONPAGED_AREA, SYSTEM_SERVICE_EXCEPTION, KERNEL_SECURITY_CHECK_FAILURE, DPC_WATCHDOG_VIOLATION.
- Crash happens during boot, on wake from sleep, or while using a specific device/app.

## Common Root Causes
- Faulty, outdated, or incompatible device drivers (especially GPU, storage, network).
- Failing RAM module or bad memory timings.
- Corrupt system files or a bad Windows Update.
- Failing disk (SSD/HDD) or loose SATA/NVMe connection.
- Overheating or an unstable overclock.
- Recently installed hardware or software conflict.

## Diagnostics / Event Log Signals
- System log: "BugCheck" event (Event ID 1001, source BugCheck) with the stop code and parameters.
- Kernel-Power Event ID 41 (system rebooted without clean shutdown).
- WHEA-Logger events indicating hardware errors.
- Minidump files in C:\Windows\Minidump for analysis.

## Recommended Fixes (require user confirmation)
1. Note the exact STOP code and any named file (e.g. nvlddmkm.sys) shown on the blue screen.
2. Boot into Safe Mode (hold Shift > Restart > Troubleshoot > Advanced options > Startup Settings) if Windows won't start normally.
3. Update or roll back the driver named in the error: Device Manager > right-click device > Update driver / Properties > Driver > Roll Back Driver.
4. Run `sfc /scannow` then `DISM /Online /Cleanup-Image /RestoreHealth` in an elevated Command Prompt.
5. Test memory: run Windows Memory Diagnostic (`mdsched.exe`) or MemTest86 overnight.
6. Check disk health: `chkdsk C: /f /r` and review SMART status.
7. Uninstall the most recent Windows Update or app if crashes started right after it.
8. Use System Restore to roll back to a known-good point if needed.

## Prevention
- Keep drivers updated from the manufacturer (not just Windows Update).
- Avoid unstable overclocks; ensure adequate cooling.
- Install Windows Updates but pause major feature updates until stable.
- Maintain backups so a clean reinstall is low-risk.
