# Proxy Configuration Issues

## Symptoms
- Some sites blocked or unreachable.
- "Unable to connect to the proxy server".
- Apps work but browsers don't (or vice versa).

## Common Root Causes
- Incorrect manual proxy settings.
- Stale PAC (auto-config) script.
- Proxy required on corporate network but set when off-network.
- Authentication required by the proxy.

## Recommended Fixes (require user confirmation)
1. Settings > Network & Internet > Proxy: verify auto/manual settings.
2. Disable manual proxy when off the corporate network.
3. Re-apply the correct PAC URL when on-network.
4. Clear browser cache and restart.
5. Confirm proxy credentials with IT.

## Prevention
- Use automatic proxy detection where possible.
- Document the correct on/off-network proxy settings.
