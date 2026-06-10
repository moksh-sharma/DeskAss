# Webcam / Camera Not Working

## Symptoms
- Camera shows a black screen or "We can't find your camera" (error 0xA00F4244).
- Camera works in one app but not another (e.g. Teams but not Zoom).
- Camera light is off during calls.

## Common Root Causes
- Camera privacy settings or a physical privacy shutter/switch.
- App lacks camera permission.
- Driver missing/outdated or disabled in Device Manager.
- Another app is holding the camera exclusively.
- Disabled in BIOS (some business laptops).

## Diagnostics / Event Log Signals
- Device Manager: "Cameras" or "Imaging devices" shows the camera disabled or with an error.
- The Windows Camera app reproduces the failure outside meeting apps.

## Recommended Fixes (require user confirmation)
1. Check the physical privacy shutter/switch and any Fn key that disables the camera.
2. Allow access: Settings > Privacy & security > Camera > turn on "Camera access" and enable it for the specific apps.
3. Test in the built-in Camera app to confirm the device itself works.
4. Close other apps that may hold the camera (Teams, Zoom, OBS) and retry.
5. Update/reinstall the camera driver: Device Manager > Cameras > Update driver, or uninstall and rescan.
6. For external webcams, try another USB port and cable.
7. Enable the camera in BIOS/UEFI if it's missing entirely (managed/business devices).

## Prevention
- Grant only trusted apps camera access.
- Keep drivers and meeting apps updated.
