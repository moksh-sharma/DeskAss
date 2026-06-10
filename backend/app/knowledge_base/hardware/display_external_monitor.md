# Display / External Monitor Problems

## Symptoms
- External monitor shows "No Signal" or isn't detected.
- Wrong resolution, blurry text, or incorrect refresh rate.
- Screen flickering, black screen, or only one of multiple monitors works.

## Common Root Causes
- Cable/port fault (HDMI/DisplayPort/USB-C) or wrong input source on the monitor.
- GPU driver issue or wrong/missing driver.
- Incorrect display mode (duplicate/extend) or resolution.
- Refresh rate not supported by the cable/monitor.
- Loose dock/adapter on laptops.

## Diagnostics / Event Log Signals
- Device Manager: Display adapter with a warning, or "Microsoft Basic Display Adapter" (generic driver = real GPU driver missing).
- System log: Display / TDR events (Event ID 4101 "display driver stopped responding and has recovered").

## Recommended Fixes (require user confirmation)
1. Check the physical connection: reseat cable, try another cable/port, select the correct input on the monitor.
2. Force detection: Settings > System > Display > Multiple displays > Detect; or press Win+P to choose Extend/Duplicate.
3. Set correct resolution and refresh rate: Display settings > Advanced display.
4. Update or reinstall the GPU driver from NVIDIA/AMD/Intel; use a clean install option.
5. If using a dock/USB-C adapter, update the dock firmware and try a direct connection to isolate the dock.
6. For flicker/TDR: lower refresh rate, replace the cable, and update the GPU driver.
7. Roll back the GPU driver if problems began after an update.

## Prevention
- Use certified cables rated for your resolution/refresh.
- Keep GPU drivers current.
