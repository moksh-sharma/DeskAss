# File/Folder Access Denied or Permission Errors

## Symptoms
- "You don't currently have permission to access this folder".
- "Access is denied" when opening, editing, or deleting files.
- Can't take ownership; changes revert.

## Common Root Causes
- NTFS permissions / ownership belong to another account (often after a Windows reinstall or migration).
- File in use or locked by a process.
- Read-only attribute or a file marked by another user/SID.
- Protected system locations requiring elevation.
- Encryption (EFS) under a different account.

## Diagnostics / Event Log Signals
- Security tab of the file/folder shows your account lacks permission.
- "You'll need to provide administrator permission" prompts.

## Recommended Fixes (require user confirmation)
1. Run the relevant app as administrator if the location is protected.
2. Check the file isn't in use: close apps holding it, or identify the lock with Resource Monitor > CPU > Associated Handles.
3. Remove the read-only attribute: right-click > Properties > untick Read-only.
4. Take ownership and grant permissions: right-click > Properties > Security > Advanced > change Owner to your account (tick "replace owner on subcontainers"), then add Full control for your user.
5. From an elevated prompt: `takeown /f "path" /r /d y` then `icacls "path" /grant <user>:F /t` (use carefully).
6. For EFS-encrypted files, sign in as the account that encrypted them or import the certificate.

## Prevention
- Migrate permissions/ownership when moving data between installs.
- Avoid editing system folder permissions unnecessarily.
