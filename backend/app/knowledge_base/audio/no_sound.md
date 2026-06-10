# No Sound / Audio Not Working

## Symptoms
- No sound from speakers or headphones.
- "No audio output device is installed" or a red X on the volume icon.
- Sound works on one output (e.g. HDMI) but not another (e.g. speakers).

## Common Root Causes
- Wrong default playback device selected.
- Muted or very low volume; app-level mute.
- Audio driver missing, disabled, or corrupt (Realtek, Intel SST, USB audio).
- Disconnected/faulty cable or jack; disabled device.
- A Windows Update changed the audio driver.

## Diagnostics / Event Log Signals
- Device Manager: "Sound, video and game controllers" shows the audio device disabled or with an error.
- System log: audio service / AudioEndpointBuilder events.
- "Audio Service is not running" message.

## Recommended Fixes (require user confirmation)
1. Check volume and mute (taskbar speaker), and the app's own volume in Volume Mixer.
2. Select the correct output: click the speaker icon > choose the right device; or Settings > System > Sound > Output.
3. Run the audio troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Audio.
4. Restart audio services: `services.msc` > "Windows Audio" and "Windows Audio Endpoint Builder" > Restart (set to Automatic).
5. Re-enable the device: Sound settings > Manage sound devices > Enable; or Device Manager > Enable device.
6. Update/reinstall the audio driver from the PC manufacturer; uninstall and rescan if corrupt.
7. For headphones, test the jack/cable on another device; check front-panel connections on desktops.

## Prevention
- Avoid third-party audio "enhancer" software that swaps drivers.
- Keep audio drivers from the OEM.
