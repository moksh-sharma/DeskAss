# Microsoft Office Activation Issues

## Symptoms
- "Product Deactivated" / "Unlicensed Product" banner.
- Office apps open in reduced-functionality (read-only) mode.
- Activation error codes (e.g. 0x80070005, 0xC004F074).

## Common Root Causes
- Sign-in/license token expired or account signed out.
- No connectivity to Microsoft activation servers (VPN/proxy).
- KMS/volume-license server unreachable.
- Conflicting or expired license.

## Recommended Fixes (require user confirmation)
1. Sign out and back into the Office account (File > Account).
2. Verify internet/VPN connectivity to Microsoft 365.
3. For volume licensing, confirm the KMS host is reachable.
4. Run the Office activation troubleshooter / `cscript ospp.vbs /act` for volume installs.
5. Repair Office (Quick then Online repair).

## Prevention
- Keep the user signed in and online periodically.
- Ensure activation endpoints are allowed by proxy/firewall.
