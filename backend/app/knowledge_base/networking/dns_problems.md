# DNS Resolution Problems

## Symptoms
- "DNS server not responding".
- Websites fail by name but work by IP.
- Intermittent access to internal/external sites.

## Common Root Causes
- Corrupt DNS cache.
- Wrong or unreachable DNS server.
- VPN/proxy overriding DNS.
- ISP DNS outage.

## Recommended Fixes (require user confirmation)
1. Flush DNS cache: `ipconfig /flushdns`.
2. Renew IP: `ipconfig /release` then `ipconfig /renew`.
3. Set a reliable DNS (e.g. 8.8.8.8 / 1.1.1.1) temporarily to test.
4. Disconnect VPN to test whether it overrides DNS.
5. Restart the router/modem if the whole network is affected.

## Prevention
- Use reliable DNS servers.
- Keep network drivers updated.
