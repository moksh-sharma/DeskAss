# VPN Authentication Issues

## Symptoms
- "Authentication failed" / "Login failed".
- MFA push not arriving or rejected.
- Certificate errors on connect.

## Common Root Causes
- Wrong credentials or expired password.
- MFA token/device out of sync.
- Expired or missing client certificate.
- Account locked or group membership changed.

## Recommended Fixes (require user confirmation)
1. Re-enter credentials carefully; confirm the password is current.
2. Approve the MFA prompt promptly; resync the authenticator if needed.
3. Check the client certificate validity and reinstall if expired.
4. Confirm with IT that the account is enabled and in the correct VPN group.
5. Sync system time (affects MFA/cert validation).

## Prevention
- Update credentials after password rotations.
- Keep authenticator app time synced.
