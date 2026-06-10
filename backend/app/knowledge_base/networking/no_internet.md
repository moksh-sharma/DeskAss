# No Internet / Limited Connectivity

## Symptoms
- "No internet" or yellow triangle on the network icon.
- Connected to Wi-Fi/Ethernet but pages won't load.
- "No internet, secured" or "Identifying..." stuck.

## Common Root Causes
- ISP/router outage or modem needs a reboot.
- IP address conflict or failed DHCP lease.
- Corrupt TCP/IP stack or DNS cache.
- Network adapter driver issue or VPN/proxy misconfiguration.
- Wrong static IP/DNS settings.

## Diagnostics / Event Log Signals
- `ipconfig /all` shows APIPA address (169.254.x.x) = no DHCP lease.
- `ping 8.8.8.8` works but `ping google.com` fails = DNS problem.
- Both pings fail = no route/connectivity.
- System log: DHCP, Dnscache, NetworkProfile events.

## Recommended Fixes (require user confirmation)
1. Reboot the modem/router (power off 30 seconds) and the PC; confirm other devices have internet to localize the fault.
2. Run the Network troubleshooter: Settings > Network & internet > Status > Network troubleshooter.
3. Renew the IP and flush DNS in an elevated prompt: `ipconfig /release`, `ipconfig /renew`, `ipconfig /flushdns`.
4. Reset the network stack: `netsh winsock reset`, `netsh int ip reset`, then restart.
5. Confirm IP/DNS are set to automatic (unless a static config is required): Network adapter > Properties > IPv4.
6. Temporarily disable VPN/proxy and third-party firewall to test.
7. Update/reinstall the network adapter driver; disable then re-enable the adapter.

## Prevention
- Use automatic IP/DNS unless static is required.
- Keep router firmware and NIC drivers updated.
