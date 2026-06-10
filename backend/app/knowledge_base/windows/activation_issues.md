# Windows Activation Problems

## Symptoms
- "Windows is not activated" watermark on the desktop.
- Errors 0xC004F074, 0xC004C003, 0x803F7001, 0x803FA067.
- Personalization settings greyed out ("You need to activate Windows").
- Activation lost after a hardware change (e.g. motherboard or disk swap).

## Common Root Causes
- Hardware change broke the digital license binding.
- Key not yet activated, or wrong edition installed.
- KMS/volume activation server unreachable on a corporate network.
- Recent reinstall without linking a Microsoft account.

## Diagnostics / Event Log Signals
- Application log: Software Protection Platform Service events with the error code.
- `slmgr /dlv` shows licensing status and remaining grace period.

## Recommended Fixes (require user confirmation)
1. Check status: Settings > System > Activation.
2. Run the Activation Troubleshooter (shown if not activated) and select "I changed hardware recently" to re-link a digital license tied to a Microsoft account.
3. Ensure the correct edition (Home vs Pro) matches the license.
4. For volume/KMS (corporate): confirm network/VPN connectivity to the KMS host; run `slmgr /ato` to retry activation.
5. Re-enter a valid product key: Settings > Activation > Change product key, or `slmgr /ipk <key>` then `slmgr /ato`.
6. Verify date/time and region are correct (affects activation).

## Prevention
- Link Windows to a Microsoft account before hardware changes.
- Record your product key / license type.
- On corporate machines, stay connected to the network periodically for KMS renewal.
