# OneDrive Sync Problems

## Symptoms
- OneDrive icon shows red X, "Sync pending", or stuck "Processing changes".
- Files not uploading/downloading; conflicts creating duplicate copies.
- "You're running out of space in OneDrive" or sign-in loops.

## Common Root Causes
- Sign-in/token expired or account issue.
- File path too long, unsupported characters, or a locked/open file.
- OneDrive storage quota full.
- Corrupt OneDrive cache or outdated client.
- Network/proxy/VPN blocking sync.

## Diagnostics / Event Log Signals
- OneDrive activity center shows the specific file/error blocking sync.
- "Processing changes" stuck for a long time on many small files.

## Recommended Fixes (require user confirmation)
1. Check the OneDrive status icon and open it to see the exact error/blocking file.
2. Confirm you're signed in and the account isn't over quota (free space or remove large items).
3. Pause and resume syncing; or quit and reopen OneDrive.
4. Fix problem files: shorten long paths, remove unsupported characters (\ / : * ? " < > |), and close files open in apps.
5. Update the OneDrive client to the latest version.
6. Reset OneDrive (keeps files): run `%localappdata%\Microsoft\OneDrive\onedrive.exe /reset`, then start OneDrive again.
7. Unlink and relink the account if reset doesn't help: OneDrive Settings > Account > Unlink this PC, then sign in again.

## Prevention
- Keep paths short; avoid special characters in names.
- Keep the client updated and quota under control.
