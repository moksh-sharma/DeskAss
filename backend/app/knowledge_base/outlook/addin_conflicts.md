# Outlook Add-in Conflicts

## Symptoms
- Slow startup, "Outlook is loading add-ins" hangs.
- Outlook disables add-ins automatically due to slow load.
- Crashes tied to a specific add-in (Teams Meeting, Zoom, CRM plugins).

## Common Root Causes
- Add-in incompatible with current Office build.
- Multiple add-ins competing at startup.
- Corrupt add-in installation.

## Recommended Fixes (require user confirmation)
1. File > Options > Add-ins > Manage: COM Add-ins > Go.
2. Disable all add-ins, then re-enable one at a time to find the culprit.
3. Reinstall or update the problematic add-in.
4. Check "Slow and Disabled COM Add-ins" dialog and re-enable if needed.

## Prevention
- Keep add-ins minimal and updated.
- Match add-in versions to the Office channel.
