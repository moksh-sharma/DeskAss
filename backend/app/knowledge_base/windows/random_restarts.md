# Random Restarts or Unexpected Shutdowns

## Symptoms
- PC reboots or powers off on its own without warning.
- Shutdowns occur under load (gaming, rendering) or seemingly at random.
- No blue screen, or the screen flashes before reboot.

## Common Root Causes
- Overheating CPU/GPU due to dust, failing fans, or dried thermal paste.
- Failing or undersized power supply (desktops) or bad battery/charger (laptops).
- Unstable RAM or overclock.
- Faulty drivers triggering silent crashes.
- Loose internal power connectors.

## Diagnostics / Event Log Signals
- System log: Kernel-Power Event ID 41 ("system has rebooted without cleanly shutting down").
- Critical thermal events; WHEA-Logger hardware error events.
- High CPU/GPU temperatures (>90°C) reported by monitoring tools.

## Recommended Fixes (require user confirmation)
1. Check temperatures with a monitoring tool under load; clean dust from fans/vents and ensure airflow.
2. Disable automatic restart to read any error: System Properties > Advanced > Startup and Recovery > untick "Automatically restart".
3. Test RAM with Windows Memory Diagnostic (`mdsched.exe`).
4. Update chipset, GPU, and storage drivers.
5. For desktops, reseat power connectors; test/replace the PSU if undersized or aging.
6. For laptops, test with a known-good charger; check battery health (`powercfg /batteryreport`).
7. Remove any recent overclock; reset BIOS/UEFI to defaults.

## Prevention
- Clean cooling components periodically.
- Use a quality, adequately rated power supply.
- Keep firmware and drivers current.
