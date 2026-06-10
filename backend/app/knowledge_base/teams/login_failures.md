# Microsoft Teams Login Failures

## Symptoms
- Stuck on loading/login screen.
- "We ran into a problem" / error codes (e.g. 0xCAA20003, 0xCAA70004).
- Repeated sign-in loops.

## Common Root Causes
- Corrupt cached credentials.
- System clock out of sync (breaks token validation).
- Network/proxy blocking authentication endpoints.
- Corrupt Teams cache.

## Recommended Fixes (require user confirmation)
1. Sign out, clear Teams cache, and sign back in.
2. Clear cached Microsoft 365 credentials in Credential Manager.
3. Ensure the system date/time is correct and set to automatic.
4. Verify network/VPN/proxy allows login.microsoftonline.com.
5. Reinstall Teams if the issue persists.

## Prevention
- Keep clock synced automatically.
- Maintain reliable network/VPN access to Microsoft 365.
