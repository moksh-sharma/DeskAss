# Application Crashes or Won't Open

## Symptoms
- An app closes immediately on launch or crashes during use.
- "Application has stopped working"; the window opens then disappears.
- App hangs ("Not Responding") and must be force-closed.

## Common Root Causes
- Corrupt app installation or settings/cache.
- Missing runtime (Visual C++ Redistributable, .NET).
- Conflicting add-in/plugin or incompatible driver (especially GPU).
- Corrupt user profile or insufficient permissions.
- Outdated app version with a known bug.

## Diagnostics / Event Log Signals
- Application log: "Application Error" (Event ID 1000) with the faulting module, or "Application Hang" (Event ID 1002).
- ".NET Runtime" errors (Event ID 1026) for managed apps.
- Faulting module points to a plugin/driver DLL.

## Recommended Fixes (require user confirmation)
1. Note the faulting module from Event Viewer (Application log, Event ID 1000) - it often names the culprit.
2. Update the app to the latest version; restart the PC.
3. Repair the app: Settings > Apps > Installed apps > app > Modify/Advanced options > Repair/Reset.
4. Clear the app's cache/settings (per-app, e.g. %AppData% folder) after backing it up.
5. Install required runtimes (latest Visual C++ Redistributables, .NET Desktop Runtime).
6. Disable add-ins/plugins; update the GPU driver if the faulting module is a graphics DLL.
7. Test in a new user profile to rule out profile corruption.

## Prevention
- Keep apps and runtimes updated.
- Only install trusted plugins/add-ins.
