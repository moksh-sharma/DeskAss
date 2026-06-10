# Disk Full / Low Storage Space

## Symptoms
- "Low Disk Space" warning; C: drive shows red.
- Can't save files, install updates, or apps misbehave.
- System slows down as free space drops below ~10%.

## Common Root Causes
- Temporary files, caches, and Windows Update leftovers.
- Large Downloads/Documents, OneDrive files kept locally.
- Hibernation file (hiberfil.sys), large page file, System Restore points.
- Duplicate/forgotten large files; recycle bin not emptied.

## Diagnostics / Event Log Signals
- Settings > System > Storage shows usage by category.
- Storage Sense recommendations.
- System log: low disk warnings (Event ID 2013 from srv).

## Recommended Fixes (require user confirmation)
1. Run Storage breakdown: Settings > System > Storage to see what's using space.
2. Enable/run Storage Sense and Disk Cleanup (`cleanmgr`) - include "Windows Update Cleanup" and "Temporary files".
3. Empty the Recycle Bin and clear `%TEMP%`.
4. Uninstall unused apps and large games: Settings > Apps > Installed apps.
5. Move large folders (Downloads, media) to another drive; set OneDrive folders to "online-only" (Files On-Demand).
6. Reduce System Restore disk usage: System Protection > Configure.
7. Disable hibernation to remove hiberfil.sys if not needed: `powercfg /h off` (elevated).

## Prevention
- Keep 15-20% of the drive free.
- Use Storage Sense to auto-clean temp files.
- Store large media on a secondary/external drive.
