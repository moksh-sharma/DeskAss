# Ethernet / Wired Connection Problems

## Symptoms
- "Network cable unplugged" though the cable is connected.
- No link lights on the port; Ethernet not detected.
- Wired connection drops intermittently or is much slower than expected.

## Common Root Causes
- Faulty cable, port, or switch.
- Network adapter driver issue or disabled NIC.
- Duplex/speed mismatch (e.g. forced 100 Mbps half-duplex).
- Power management turning off the adapter.

## Diagnostics / Event Log Signals
- Device Manager: Ethernet adapter disabled or with an error.
- No link LED on the NIC/switch port.
- `ethtool`-style info via adapter Properties; link speed lower than rated.

## Recommended Fixes (require user confirmation)
1. Reseat or replace the Ethernet cable; try a different wall port/switch port. Verify link lights.
2. Enable the adapter: Settings > Network & internet > Advanced network settings, or `ncpa.cpl` > right-click > Enable.
3. Update/reinstall the Ethernet driver from the PC manufacturer.
4. Set Speed & Duplex to "Auto Negotiation": Device Manager > adapter > Properties > Advanced.
5. Disable power saving: adapter > Properties > Power Management > untick "Allow the computer to turn off this device".
6. Reset the stack if needed: `netsh int ip reset`, `netsh winsock reset`, restart.
7. Test another device on the same cable/port to isolate the PC vs the network.

## Prevention
- Use good-quality cables (Cat5e/Cat6).
- Keep NIC drivers updated; disable adapter power-off on desktops.
