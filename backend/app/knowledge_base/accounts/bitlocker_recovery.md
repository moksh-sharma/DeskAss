# BitLocker Recovery Key Prompt

## Symptoms
- Blue "BitLocker recovery" screen on boot asking for a 48-digit key.
- Happens after a BIOS update, hardware change, or Windows update.
- Can't access an encrypted drive without the key.

## Common Root Causes
- TPM/Secure Boot state changed (BIOS update, settings change, CMOS reset).
- Hardware change (motherboard, TPM, sometimes adding/removing devices).
- Firmware/boot order changes that alter the measured boot.
- Forgotten password on an encrypted external drive.

## Diagnostics / Event Log Signals
- BitLocker recovery screen shows a "Recovery key ID" to match the correct key.
- Event log (once in Windows): BitLocker-API / BitLocker-Driver events.

## Recommended Fixes (require user confirmation)
1. Find the recovery key: sign in at https://account.microsoft.com/devices/recoverykey (personal Microsoft account), or your work/school Azure AD account, matching the Key ID shown.
2. For corporate devices, IT can retrieve the key from Azure AD/Intune or Active Directory; contact the help desk with the Key ID.
3. Enter the 48-digit key to unlock and boot.
4. After booting, prevent repeats: if a BIOS update triggered it, ensure Secure Boot/TPM settings match the original; or suspend BitLocker before firmware changes (`manage-bde -protectors -disable C:`), update, then resume.
5. Verify the key is backed up: Control Panel > BitLocker > Back up your recovery key.

## Prevention
- Always back up the recovery key to your Microsoft/Azure account.
- Suspend BitLocker before BIOS/firmware updates or hardware changes.
