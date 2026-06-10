# Device Driver Problems

## Symptoms
- A device shows a yellow exclamation mark in Device Manager.
- Error codes: Code 10 (cannot start), Code 28 (no drivers installed), Code 43 (device reported a problem), Code 31, Code 45.
- Hardware stops working after an update; intermittent device dropouts.

## Common Root Causes
- Missing, outdated, corrupt, or incompatible driver.
- A Windows Update replaced a working driver with a generic one.
- Conflicting drivers or leftover files from a previous device.
- Hardware fault presenting as a driver error.

## Diagnostics / Event Log Signals
- Device Manager shows the device with an error code (right-click > Properties > General).
- System log: events from source "Microsoft-Windows-Kernel-PnP" or driver-specific sources.
- DriverFrameworks events for misbehaving drivers.

## Recommended Fixes (require user confirmation)
1. Open Device Manager (`devmgmt.msc`) and locate the flagged device.
2. Update driver: right-click > Update driver > Search automatically; or install the latest from the manufacturer's website.
3. If the problem started after an update, roll back: Properties > Driver tab > Roll Back Driver.
4. Uninstall the device (tick "Delete the driver software" if available), then scan for hardware changes to reinstall cleanly.
5. For Code 43 on USB/GPU, try a different port, reseat the device, and update chipset/USB drivers.
6. Run `sfc /scannow` if multiple devices fail (system-level corruption).
7. Check BIOS/UEFI is up to date for chipset-related device issues.

## Prevention
- Install drivers from the manufacturer, matching your exact model.
- Create a restore point before driver changes.
- Avoid third-party "driver updater" tools.
