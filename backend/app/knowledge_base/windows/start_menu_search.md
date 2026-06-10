# Start Menu, Taskbar, or Search Not Working

## Symptoms
- Clicking Start does nothing; the Start menu won't open.
- Taskbar is frozen, missing icons, or unresponsive.
- Windows Search returns no results or the search box won't type.

## Common Root Causes
- Corrupt user profile or broken Start/Search app packages.
- Windows Search index corruption.
- A bad update affecting the shell (ShellExperienceHost / StartMenuExperienceHost).
- Explorer.exe in a bad state.

## Diagnostics / Event Log Signals
- Application log: errors from StartMenuExperienceHost, SearchUI, or ShellExperienceHost.
- AppModel-Runtime events for failing UWP packages.

## Recommended Fixes (require user confirmation)
1. Restart Windows Explorer: Task Manager > Details/Processes > select "Windows Explorer" > Restart.
2. Run the Search troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Search and Indexing.
3. Rebuild the search index: Control Panel > Indexing Options > Advanced > Rebuild.
4. Re-register shell apps in elevated PowerShell: `Get-AppxPackage Microsoft.Windows.ShellExperienceHost | Foreach {Add-AppxPackage -DisableDevelopmentMode -Register "$($_.InstallLocation)\AppXManifest.xml"}` and the same for `Microsoft.Windows.StartMenuExperienceHost`.
5. Run `sfc /scannow` and `DISM /Online /Cleanup-Image /RestoreHealth`.
6. Create a new local user account to test if the profile is corrupt; migrate data if so.

## Prevention
- Avoid forced shutdowns that corrupt profiles.
- Keep Windows updated to receive shell fixes.
