# Bluetooth Not Working / Won't Pair

## Symptoms
- Bluetooth toggle is missing from Settings/Action Center.
- Devices won't pair, or pair then disconnect repeatedly.
- Audio devices connect but have no sound or poor quality.

## Common Root Causes
- Bluetooth driver missing, outdated, or disabled.
- Bluetooth Support Service stopped.
- Airplane mode on, or radio disabled in BIOS.
- Interference or the device not in pairing mode.
- Driver replaced by a Windows Update.

## Diagnostics / Event Log Signals
- Device Manager: Bluetooth adapter missing, disabled, or with an error code.
- System log: BTHUSB / BthLEEnum events.
- "Bluetooth" category absent from Device Manager entirely (driver not installed).

## Recommended Fixes (require user confirmation)
1. Ensure airplane mode is off and Bluetooth is enabled (Settings > Bluetooth & devices).
2. Confirm the "Bluetooth Support Service" is running: `services.msc` > set to Automatic and Start.
3. In Device Manager, enable or update the Bluetooth adapter; reinstall the driver from the manufacturer if needed.
4. Run the Bluetooth troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Bluetooth.
5. Remove and re-pair the device: Settings > Bluetooth & devices > device > Remove, then put the device in pairing mode and re-add.
6. For audio: set the device as default in Sound settings; ensure the "Hands-Free"/"Stereo" profile is correct.
7. Update BIOS/UEFI and chipset drivers; check the wireless card isn't disabled in BIOS.

## Prevention
- Keep wireless drivers updated.
- Charge Bluetooth peripherals; reduce 2.4 GHz interference.
