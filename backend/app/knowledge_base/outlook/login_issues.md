# Outlook Login / Authentication Issues

## Symptoms
- Repeated password prompts ("Need Password").
- "Cannot connect to the server".
- Stuck on "Trying to connect..." / disconnected.

## Common Root Causes
- Cached/expired credentials in Windows Credential Manager.
- Modern Authentication / MFA token expired.
- Network or proxy blocking Exchange/Microsoft 365 endpoints.
- Incorrect autodiscover configuration.

## Recommended Fixes (require user confirmation)
1. Clear cached credentials: Control Panel > Credential Manager > Windows Credentials > remove Office/Outlook entries.
2. Sign out and back into the Office account: File > Office Account > Sign out.
3. Verify internet/VPN connectivity and that Microsoft 365 endpoints are reachable.
4. Recreate the Outlook profile.
5. Confirm the account password / MFA is current.

## Prevention
- Keep credentials updated after password changes.
- Ensure VPN/proxy allows Microsoft 365 endpoints.
