# Microphone Not Working

## Symptoms
- Others can't hear you in calls; mic shows no input level.
- "Microphone not detected" or wrong mic selected.
- Mic is very quiet, distorted, or picks up heavy background noise.

## Common Root Causes
- Microphone privacy settings or app permissions blocked.
- Wrong default input device.
- Muted hardware switch or low input level.
- Driver issue; another app holding the mic.

## Diagnostics / Event Log Signals
- Settings > Sound > Input shows no level movement when speaking.
- Device Manager: audio input device disabled or with an error.

## Recommended Fixes (require user confirmation)
1. Allow access: Settings > Privacy & security > Microphone > turn on "Microphone access" and enable it for the app (Teams, Zoom, browser).
2. Select the correct input and raise the level: Settings > System > Sound > Input > choose device, set volume, and test.
3. Check for a physical mute switch (headset inline mute, laptop Fn key).
4. Run the recording/audio troubleshooter: Settings > System > Troubleshoot > Other troubleshooters.
5. Disable exclusive mode if apps fight over the mic: Sound Control Panel > Recording > device > Properties > Advanced > untick "Allow applications to take exclusive control".
6. Update/reinstall the audio driver.
7. For noise, enable noise suppression in the app or Windows (Sound settings > device > Audio enhancements).

## Prevention
- Grant mic access only to trusted apps.
- Keep the correct default device set.
