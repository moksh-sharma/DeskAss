# Wi-Fi Connectivity Problems

## Symptoms
- Can't connect to Wi-Fi or frequent drops.
- "No internet, secured".
- Slow or unstable wireless.

## Common Root Causes
- Weak signal / distance from access point.
- Outdated or corrupt wireless adapter driver.
- Incorrect Wi-Fi password or captive portal.
- IP/DHCP conflict.
- Power management turning off the adapter.

## Recommended Fixes (require user confirmation)
1. Toggle Wi-Fi off/on; forget and reconnect to the network.
2. Run the Windows Network troubleshooter.
3. Update or reinstall the wireless adapter driver.
4. Reset the network stack: `netsh winsock reset` and `netsh int ip reset`.
5. Disable adapter power saving (Device Manager > adapter > Power Management).
6. Move closer to the access point to rule out signal issues.

## Prevention
- Keep adapter drivers updated.
- Disable aggressive power saving on the adapter.
