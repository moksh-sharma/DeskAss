# Scanner Not Working

## Symptoms
- Scanner not detected by Windows Scan or the manufacturer app.
- "No scanners were detected" or scanning hangs/fails.
- All-in-one prints but won't scan.

## Common Root Causes
- WIA (Windows Image Acquisition) service stopped.
- Missing/outdated scanner driver or TWAIN/WIA component.
- USB/network connection issue.
- Firewall blocking network scan-to-PC.

## Diagnostics / Event Log Signals
- Device Manager: imaging device missing or with an error.
- Services: "Windows Image Acquisition (WIA)" not running.
- System log: WIA / StillImage events.

## Recommended Fixes (require user confirmation)
1. Ensure the WIA service is running: `services.msc` > Windows Image Acquisition (WIA) > Start, set to Automatic (also check "Shell Hardware Detection" and "RPC").
2. Verify the connection: try another USB port/cable, or confirm the network scanner's IP is reachable.
3. Install the full driver/software package from the manufacturer (not just the print driver).
4. Test with the built-in Windows Scan app to isolate app vs device.
5. For scan-to-PC over network, allow the app through Windows Defender Firewall.
6. Reinstall the imaging device: Device Manager > uninstall > scan for hardware changes.

## Prevention
- Install the complete OEM driver suite.
- Keep firmware updated on networked all-in-ones.
