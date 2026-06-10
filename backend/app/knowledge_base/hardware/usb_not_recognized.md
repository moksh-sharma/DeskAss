# USB Device Not Recognized

## Symptoms
- "USB device not recognized" or "Unknown USB Device (Device Descriptor Request Failed)".
- USB drive, mouse, keyboard, or dongle not detected when plugged in.
- Device works in one port but not another, or disconnects randomly.

## Common Root Causes
- Faulty port, cable, or the device itself.
- Corrupt or outdated USB controller drivers.
- USB selective suspend powering down the port.
- Insufficient power on a hub; chipset driver issues.
- Drive needs a letter or is unformatted/uninitialized.

## Diagnostics / Event Log Signals
- Device Manager shows "Unknown USB Device" or a device with Code 43.
- System log: Kernel-PnP and USB events on insert.
- Disk Management shows a connected drive with no letter or as "Not initialized".

## Recommended Fixes (require user confirmation)
1. Try another USB port (preferably directly on the PC, not a hub) and a different cable; test the device on another PC.
2. In Device Manager, expand "Universal Serial Bus controllers", uninstall the flagged device, then "Scan for hardware changes".
3. Disable USB selective suspend: Power Options > Advanced > USB settings > USB selective suspend setting > Disabled.
4. Update chipset and USB drivers from the manufacturer.
5. For storage that's detected but has no letter: Disk Management (`diskmgmt.msc`) > assign a drive letter, or initialize/format a new disk (warning: formatting erases data).
6. Run the Hardware and Devices troubleshooter (`msdt.exe -id DeviceDiagnostic`).
7. Update BIOS/UEFI if multiple ports fail.

## Prevention
- Safely eject drives before removal.
- Avoid overloading unpowered hubs.
- Keep chipset drivers updated.
