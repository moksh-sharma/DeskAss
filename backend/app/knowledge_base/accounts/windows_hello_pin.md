# Windows Hello PIN / Fingerprint / Face Sign-in Problems

## Symptoms
- "Something went wrong" when setting up or using a PIN.
- Fingerprint or face recognition stops working.
- "Your PIN is no longer available" after an update.
- Errors 0x80090016, 0x801c004d, or PIN setup loops.

## Common Root Causes
- Corrupt NGC (Next Generation Credentials) folder storing Hello data.
- TPM issue or cleared TPM.
- Biometric driver problem or dirty/blocked sensor.
- Account/policy changes after a password reset.

## Diagnostics / Event Log Signals
- Application log: HelloForBusiness / NGC events.
- Device Manager: biometric/IR camera device with an error.
- TPM status in `tpm.msc` shows not ready.

## Recommended Fixes (require user confirmation)
1. Sign in with your password, then re-add the PIN: Settings > Accounts > Sign-in options > PIN > "I forgot my PIN".
2. For fingerprint/face, remove and re-enroll the biometric; clean the sensor; ensure the IR camera/fingerprint driver is installed and updated.
3. Reset Hello credentials by clearing the NGC folder (advanced): take ownership of `C:\Windows\ServiceProfiles\LocalService\AppData\Local\Microsoft\Ngc`, delete its contents, restart, then set up the PIN again.
4. Verify the TPM is ready (`tpm.msc`); if cleared, re-initialize per OEM guidance (back up BitLocker key first).
5. Run `sfc /scannow` if multiple sign-in components fail.
6. For "managed by organization", coordinate with IT on Hello for Business policy.

## Prevention
- Keep biometric drivers and Windows updated.
- Back up the BitLocker key before TPM operations.
