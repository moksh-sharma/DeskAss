# Mouse or Touchpad Not Working

## Symptoms
- Cursor doesn't move, jumps, or lags.
- Touchpad disabled or not responding; clicks not registering.
- Scrolling or gestures stopped working.

## Common Root Causes
- Touchpad turned off via a function key or in Settings.
- Driver missing/outdated (Synaptics, Precision Touchpad, ELAN).
- USB/Bluetooth connection issue or low battery on wireless mouse.
- Dirty sensor or surface; Filter Keys/pointer settings.

## Diagnostics / Event Log Signals
- Device Manager: "Mice and other pointing devices" shows the device with an error or missing.
- HID device events in the System log.

## Recommended Fixes (require user confirmation)
1. Re-enable the touchpad: press the touchpad function key (often Fn+F-key), or Settings > Bluetooth & devices > Touchpad > On.
2. For wireless mice, replace batteries, re-seat the USB receiver, or re-pair Bluetooth.
3. Update/reinstall the pointing device driver from the manufacturer (Precision Touchpad recommended where supported).
4. Adjust pointer behavior: Settings > Bluetooth & devices > Mouse / Touchpad (speed, sensitivity, palm rejection).
5. Clean the optical sensor and use a non-glossy surface or mouse pad.
6. Run the Hardware and Devices troubleshooter (`msdt.exe -id DeviceDiagnostic`).
7. Test another mouse to isolate hardware vs driver.

## Prevention
- Keep touchpad/chipset drivers updated.
- Keep the sensor and surface clean.
