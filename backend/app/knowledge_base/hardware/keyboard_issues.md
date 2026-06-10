# Keyboard Not Working or Typing Wrong Characters

## Symptoms
- Some or all keys don't respond.
- Wrong characters appear (e.g. @ and " swapped), or numbers don't type.
- Keyboard works in BIOS but not in Windows, or vice versa.

## Common Root Causes
- Wrong keyboard layout/region (e.g. US vs UK).
- Num Lock / Filter Keys / Sticky Keys enabled.
- Driver issue or USB/Bluetooth connection fault.
- Spilled liquid or hardware failure.
- Fast startup leaving the keyboard in a bad state.

## Diagnostics / Event Log Signals
- Device Manager: keyboard device with an error code.
- Wrong characters typically indicate a layout mismatch, not hardware.

## Recommended Fixes (require user confirmation)
1. For wrong characters: fix layout - Settings > Time & language > Language & region > set the correct keyboard layout; remove extra layouts.
2. Disable accessibility filters: Settings > Accessibility > Keyboard > turn off Sticky Keys, Filter Keys, Toggle Keys.
3. Check Num Lock if the number pad types arrows or nothing.
4. Reconnect: try another USB port, re-pair Bluetooth, or replace batteries.
5. Reinstall the driver: Device Manager > Keyboards > uninstall > scan for hardware changes.
6. Run the Keyboard troubleshooter (`msdt.exe -id KeyboardDiagnostic`).
7. Test in another app and on the sign-in screen to isolate app vs system; test an external keyboard on laptops.

## Prevention
- Keep the correct single layout configured.
- Keep liquids away from the keyboard.
