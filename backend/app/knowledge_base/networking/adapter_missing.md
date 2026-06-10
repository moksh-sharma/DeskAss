# Network Adapter Missing or Disabled

## Symptoms
- No Wi-Fi or Ethernet option in Settings.
- "Can't connect to this network"; no networks listed.
- Network adapter absent from Device Manager or shows an error.

## Common Root Causes
- Driver missing/corrupt or a Windows Update removed it.
- Adapter disabled in Windows or in BIOS.
- Airplane mode on; WLAN AutoConfig service stopped.
- Hardware failure of the network card.

## Diagnostics / Event Log Signals
- Device Manager: adapter missing, disabled, or with Code 10/Code 56.
- `ipconfig /all` lists no adapters.
- Services: "WLAN AutoConfig" not running.

## Recommended Fixes (require user confirmation)
1. Turn off airplane mode and confirm the physical wireless switch/Fn key is on.
2. Show hidden devices in Device Manager (View > Show hidden devices) and enable the adapter.
3. Start required services: `services.msc` > "WLAN AutoConfig" (Wi-Fi) / "Network Connections" > Automatic + Start.
4. Reinstall the driver: Device Manager > uninstall the adapter > Scan for hardware changes; or install the driver from another PC via USB.
5. Run Network reset: Settings > Network & internet > Advanced network settings > Network reset (reinstalls adapters).
6. Enable the NIC/WLAN in BIOS/UEFI if it's disabled there.
7. If still absent, the card may have failed - test a USB Wi-Fi/Ethernet adapter.

## Prevention
- Keep a copy of the network driver offline for recovery.
- Update drivers from the OEM.
