# Failing Hard Drive / SSD

## Symptoms
- Loud clicking/grinding (HDD), or very slow file access.
- Files/folders disappear or become corrupt; "cyclic redundancy check" errors.
- Frequent freezes; Windows reports disk errors or fails to boot.
- SMART warning: "Windows detected a hard disk problem".

## Common Root Causes
- Bad sectors or mechanical failure (HDD).
- SSD wear-out (exhausted write endurance) or controller failure.
- Loose/failing SATA or NVMe connection.
- Overheating storage.

## Diagnostics / Event Log Signals
- System log: disk Event ID 7 ("bad block"), 51 ("error during paging"), 153 (I/O retries).
- SMART status: reallocated sectors, pending sectors, or "Caution/Bad" health.
- "PredictFailure" WMI flag set true.

## Recommended Fixes (require user confirmation)
1. Back up important data immediately before troubleshooting - a failing drive can die at any moment.
2. Check SMART health with the vendor tool (e.g. CrystalDiskInfo, Samsung Magician, WD Dashboard).
3. Run `chkdsk C: /f /r` to detect and remap bad sectors (run during the next reboot for the system drive).
4. Update the SSD firmware from the manufacturer.
5. Reseat SATA/NVMe and power connectors; try another port/cable (desktops).
6. Ensure the drive isn't overheating; improve airflow.
7. If SMART shows failure or errors persist, replace the drive and restore from backup.

## Prevention
- Keep regular backups (3-2-1 rule).
- Monitor SMART health periodically.
- Don't fill SSDs to 100%; leave free space for wear leveling.
