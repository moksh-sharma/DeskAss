# Disk Space and Disk Performance Issues

## Symptoms
- "Low disk space" warnings.
- Disk usage at 100% in Task Manager.
- Slow file operations, app installs failing.

## Common Root Causes
- Drive nearly full (<10% free).
- Temporary files, Windows Update cache, hibernation file bloat.
- Failing drive (SMART errors) or fragmented HDD.
- Disk 100% caused by SysMain/Superfetch, Windows Search, or a failing disk.

## Diagnostics To Check
- Disk usage_percent > 90%, low free_gb.
- Event Log: disk/ntfs/volume errors indicate hardware problems.

## Recommended Fixes (require user confirmation)
1. Run Disk Cleanup (cleanmgr) and remove temporary + system files.
2. Clear %TEMP% and Windows Update cache.
3. Empty the Recycle Bin.
4. Uninstall unused applications.
5. Move large files to network/cloud storage.
6. Run `chkdsk` if disk errors appear in the event log.

## Prevention
- Keep 15-20% free space.
- Enable Storage Sense for automatic cleanup.
- Monitor SMART health for early drive failure warnings.
