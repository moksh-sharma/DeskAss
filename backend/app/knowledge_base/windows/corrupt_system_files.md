# Corrupt System Files

## Symptoms
- Random errors, missing DLL messages, features failing to open (Settings, Start menu, Search).
- Windows Update fails repeatedly with component store errors.
- Apps crash inconsistently with no clear cause.

## Common Root Causes
- Improper shutdown or power loss during writes.
- Disk errors / bad sectors.
- Malware tampering with system files.
- Interrupted or failed updates.

## Diagnostics / Event Log Signals
- CBS.log (C:\Windows\Logs\CBS\CBS.log) shows "cannot repair member file" entries.
- Application errors referencing system DLLs.
- DISM reports "The component store is repairable".

## Recommended Fixes (require user confirmation)
1. Open an elevated Command Prompt or PowerShell (Run as administrator).
2. Run `sfc /scannow` to scan and repair protected system files.
3. If SFC cannot fix everything, run `DISM /Online /Cleanup-Image /RestoreHealth` (needs internet), then run `sfc /scannow` again.
4. If DISM fails, supply a known-good source: `DISM /Online /Cleanup-Image /RestoreHealth /Source:wim:X:\sources\install.wim:1 /LimitAccess` (X = mounted ISO).
5. Run `chkdsk C: /f /r` to fix underlying disk errors.
6. If corruption persists, perform an in-place repair install using the Media Creation Tool (keeps files and apps).

## Prevention
- Use a UPS or avoid abrupt power loss.
- Keep antivirus active; scan regularly.
- Replace disks showing SMART warnings.
