# Can't Sign In / Password and Account Lockout

## Symptoms
- "The password is incorrect" though it seems right.
- "Your account has been locked"; too many sign-in attempts.
- Can't sign in after a password change; PIN not accepted.
- Temporary profile loaded ("We can't sign in to your account").

## Common Root Causes
- Caps Lock / wrong keyboard layout altering typed characters.
- Recent Microsoft account password change not synced to the PC (needs internet once).
- Account lockout policy triggered (corporate).
- Corrupt user profile.
- Cached domain credentials out of date.

## Diagnostics / Event Log Signals
- Security log: Event ID 4625 (failed logon) with a status/sub-status code; 4740 (account locked).
- "Temporary profile" warning in the System log (user profile service).

## Recommended Fixes (require user confirmation)
1. Check Caps Lock and the keyboard layout indicator on the lock screen; type the password into a visible field to verify.
2. For a Microsoft account, reset the password at account.microsoft.com from another device, then sign in with internet connected so it syncs.
3. For lockouts (corporate), wait the lockout duration or contact IT/AD admin to unlock; verify no old credentials are stored (e.g. mapped drives, Outlook).
4. Sign in with a PIN if the password syncs fail, or use "I forgot my PIN" to reset (requires account verification).
5. Update cached domain credentials by connecting to the corporate network/VPN and signing in.
6. For a corrupt/temporary profile, sign in as another admin and repair or recreate the profile (back up data first).

## Prevention
- Keep recovery info (phone/email) current on the Microsoft account.
- Update stored credentials after password changes.
