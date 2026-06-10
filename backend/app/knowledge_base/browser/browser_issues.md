# Browser Problems (Chrome / Edge / Firefox)

## Symptoms
- Pages won't load, load slowly, or show errors (ERR_CONNECTION, ERR_NAME_NOT_RESOLVED, SSL errors).
- Browser is slow, freezes, or crashes ("Aw, Snap!").
- Redirects, pop-ups, or a changed homepage/search engine.

## Common Root Causes
- Corrupt cache/cookies or a bad browser profile.
- Problematic or malicious extensions.
- Outdated browser; too many tabs exhausting RAM.
- DNS/network issues; wrong system date causing SSL errors.
- Hardware acceleration / GPU driver conflict.

## Diagnostics / Event Log Signals
- Same sites load in another browser = browser-specific issue.
- All browsers fail = network/DNS (see networking docs).
- SSL/date errors point to a wrong system clock.

## Recommended Fixes (require user confirmation)
1. Update the browser to the latest version and restart it.
2. Clear cache and cookies (Settings > Privacy > Clear browsing data).
3. Test in an Incognito/Private window (disables extensions) - if it works, disable extensions one by one to find the culprit.
4. Remove suspicious extensions and reset the homepage/search engine.
5. Fix SSL/date errors by setting the correct system date/time (automatic).
6. Toggle hardware acceleration off (or update the GPU driver) if pages glitch/crash.
7. Reset the browser to defaults, or create a fresh profile, if problems persist.
8. For network errors, flush DNS (`ipconfig /flushdns`) and check VPN/proxy.

## Prevention
- Keep the browser and extensions minimal and updated.
- Avoid installing extensions from unknown sources.
