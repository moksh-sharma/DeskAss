# Outlook Crashes or Hangs

## Symptoms
- Outlook crashes on launch or randomly closes.
- "Microsoft Outlook has stopped working".
- Outlook freezes ("Not Responding"), especially with large mailboxes.

## Common Root Causes
- Faulty or outdated add-ins (COM add-ins).
- Corrupt Outlook profile or OST/PST data file.
- Oversized mailbox / PST file.
- Conflicting antivirus email scanning.
- Outdated Office build.

## Diagnostics / Event Log Signals
- Application Error / Application Hang events with faulting module outlook.exe.
- "Faulting application name: OUTLOOK.EXE" in the Application log.
- DLL faults referencing add-in modules.

## Recommended Fixes (require user confirmation)
1. Start Outlook in Safe Mode: hold Ctrl while launching, or run `outlook.exe /safe`.
2. If stable in Safe Mode, disable add-ins: File > Options > Add-ins > COM Add-ins.
3. Repair the Outlook data file with `scanpst.exe`.
4. Create a new Outlook profile (Control Panel > Mail > Show Profiles).
5. Run an Office Quick Repair, then Online Repair if needed.
6. Update Office to the latest build.

## Prevention
- Keep mailbox/PST under recommended size limits (archive old mail).
- Only install trusted add-ins.
- Keep Office updated.
