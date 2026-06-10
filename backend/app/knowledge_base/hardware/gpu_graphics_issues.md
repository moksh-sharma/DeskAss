# Graphics / GPU Problems (Artifacts, Crashes, TDR)

## Symptoms
- Screen artifacts, weird colors, or graphical glitches.
- Games/apps crash with "display driver stopped responding and has recovered".
- Black screen under GPU load; poor performance or stutter.

## Common Root Causes
- Corrupt or outdated GPU driver.
- Overheating GPU (dust, failing fans).
- Unstable overclock or insufficient power.
- Failing GPU hardware or VRAM.

## Diagnostics / Event Log Signals
- System log: Event ID 4101 (nvlddmkm / amdkmdag / igfx) "display driver stopped responding".
- WHEA-Logger errors for PCIe/GPU.
- High GPU temperatures under load.

## Recommended Fixes (require user confirmation)
1. Clean-install the latest GPU driver: use the vendor installer with the "clean install" option, or DDU (Display Driver Uninstaller) in Safe Mode for a fresh start.
2. Check GPU temperatures under load; clean dust and ensure case airflow.
3. Remove any GPU overclock; set clocks to stock.
4. For desktops, reseat the GPU and its power connectors; verify the PSU is adequate.
5. Increase the TDR delay only as a diagnostic step if recommended; prefer fixing the driver/thermals first.
6. Test the GPU in another system or with the integrated GPU to isolate hardware failure.

## Prevention
- Keep GPU drivers updated; avoid mixing driver versions.
- Maintain cooling and adequate power headroom.
