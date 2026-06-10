# Firewall Blocking an App or Connection

## Symptoms
- An app can't connect to the internet or a network resource.
- Server/sharing/remote desktop unreachable from other devices.
- Connection works with the firewall off but not on.

## Common Root Causes
- App not allowed through Windows Defender Firewall.
- Blocking inbound/outbound rule, or wrong network profile (Public vs Private).
- Third-party firewall/security suite blocking traffic.
- Required port closed.

## Diagnostics / Event Log Signals
- Security log (with firewall auditing) shows dropped packets.
- Windows Firewall with Advanced Security shows blocking rules.
- App connects when firewall is temporarily disabled (diagnostic only).

## Recommended Fixes (require user confirmation)
1. Allow the app: Settings > Privacy & security > Windows Security > Firewall & network protection > Allow an app through firewall; tick Private (and Public if needed).
2. Confirm the network profile is correct: a home/work LAN should be "Private", not "Public" (Settings > Network > properties).
3. Create a specific rule for the port/app in "Windows Defender Firewall with Advanced Security" (`wf.msc`) instead of disabling the firewall.
4. Check third-party security suites for their own firewall blocking the app.
5. Reset firewall to defaults if rules are corrupt: `netsh advfirewall reset` (re-add custom rules afterward).
6. Re-enable the firewall after testing - do not leave it off.

## Prevention
- Add explicit allow rules rather than disabling the firewall.
- Keep the correct network profile set.
