# IP Address Conflict

## Symptoms
- "Windows has detected an IP address conflict".
- Intermittent loss of network access; some sites/resources unreachable.
- Connection works then drops when another device joins.

## Common Root Causes
- Two devices assigned the same static IP.
- DHCP scope overlap or a rogue DHCP server.
- A reserved static IP also handed out by DHCP.

## Diagnostics / Event Log Signals
- System log: Tcpip Event ID 4198/4199 (address conflict).
- `ipconfig /all` shows the conflicting address.
- `arp -a` reveals duplicate IP-to-MAC mappings.

## Recommended Fixes (require user confirmation)
1. Release and renew the DHCP lease: `ipconfig /release` then `ipconfig /renew`.
2. If using a static IP, change it to an unused address outside the DHCP range, or switch to automatic (DHCP).
3. On the router, reserve a unique IP (DHCP reservation) for devices that need a fixed address.
4. Check for a second/rogue DHCP server (e.g. a misconfigured router or hotspot) and disable it.
5. Reboot the router to refresh the DHCP table if conflicts persist.

## Prevention
- Use DHCP reservations instead of manual static IPs where possible.
- Keep static IPs outside the DHCP pool.
