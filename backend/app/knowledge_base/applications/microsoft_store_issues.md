# Microsoft Store Apps Not Working

## Symptoms
- Microsoft Store won't open or closes instantly.
- App downloads stuck or fail with codes 0x80131500, 0x80073CF9, 0x803F8001.
- Installed Store apps crash or won't launch.

## Common Root Causes
- Corrupt Store cache.
- Wrong date/time/region settings.
- Corrupt app packages or pending updates.
- Account/licensing sync issue.

## Diagnostics / Event Log Signals
- Application log: AppModel-Runtime / AppXDeployment errors.
- Store error code shown in the download list.

## Recommended Fixes (require user confirmation)
1. Reset the Store cache: run `wsreset.exe` (a blank window opens, then the Store launches).
2. Correct date, time, and region: Settings > Time & language (wrong values break licensing).
3. Run the troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Windows Store Apps.
4. Update apps: Microsoft Store > Library > Get updates.
5. Repair/Reset the Store app: Settings > Apps > Installed apps > Microsoft Store > Advanced options > Repair, then Reset.
6. Re-register Store/app packages in elevated PowerShell: `Get-AppxPackage -allusers Microsoft.WindowsStore | Foreach {Add-AppxPackage -DisableDevelopmentMode -Register "$($_.InstallLocation)\AppXManifest.xml"}`.
7. Sign out and back into the Store with the correct Microsoft account.

## Prevention
- Keep date/time automatic and region correct.
- Install app updates regularly.
