# VPN Connection Problems

## Symptoms
- VPN will not connect or times out.
- Connects then immediately drops.
- Connected but no access to internal resources.

## Common Root Causes
- No/unstable underlying internet connection.
- Wrong server address or expired client.
- Firewall/ISP blocking VPN ports (UDP 500/4500, TCP 443).
- DNS or split-tunnel misconfiguration.
- Outdated VPN client (AnyConnect, GlobalProtect, OpenVPN).

## Diagnostics To Check
- internet_connected must be true before VPN can work.
- Event Log: VPN client service errors.

## Recommended Fixes (require user confirmation)
1. Verify basic internet connectivity first.
2. Restart the VPN client and reconnect.
3. Update the VPN client to the latest version.
4. Try a different network (e.g. mobile hotspot) to rule out firewall blocks.
5. Flush DNS (`ipconfig /flushdns`) and reset the adapter.
6. Reinstall the VPN client if the virtual adapter is broken.

## Prevention
- Keep the VPN client updated.
- Ensure required ports are allowed on local firewalls.
