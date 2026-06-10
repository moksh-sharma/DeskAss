# .NET / Visual C++ Runtime Errors

## Symptoms
- "The application requires .NET" or ".NET Runtime" errors on launch.
- "VCRUNTIME140.dll / MSVCP140.dll is missing".
- App crashes with Event ID 1026 (.NET Runtime) in the Application log.
- "0xc000007b" application error.

## Common Root Causes
- Missing or corrupt Visual C++ Redistributable.
- Missing/incompatible .NET runtime (Framework or .NET Desktop Runtime).
- Mixed 32-bit/64-bit runtime mismatch.
- Corrupt runtime installation.

## Diagnostics / Event Log Signals
- Application log: ".NET Runtime" Event ID 1026 with the failing assembly.
- "Application Error" naming vcruntime/msvcp DLLs.

## Recommended Fixes (require user confirmation)
1. Install the latest Microsoft Visual C++ Redistributable (both x86 and x64) from Microsoft.
2. Install the required .NET: for older apps, enable ".NET Framework 3.5" via Settings > Optional features / Windows Features; for modern apps, install the ".NET Desktop Runtime" version the app needs.
3. Match the app's architecture: a 32-bit app needs the x86 redistributable even on 64-bit Windows.
4. Repair the runtime: Settings > Apps > Installed apps > Microsoft Visual C++ ... > Modify > Repair.
5. Run `sfc /scannow` and `DISM /Online /Cleanup-Image /RestoreHealth` if framework files are corrupt.
6. Reinstall the application after the runtimes are in place.

## Prevention
- Keep Visual C++ Redistributables and .NET runtimes updated.
- Install both x86 and x64 redistributables.
