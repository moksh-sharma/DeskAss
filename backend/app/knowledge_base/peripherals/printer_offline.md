# Printer Offline or Not Printing

## Symptoms
- Printer shows "Offline" in Settings even when powered on.
- Jobs stay in the queue and never print.
- "Printer not found" on the network; can't add the printer.

## Common Root Causes
- Print spooler service stuck or stopped.
- "Use Printer Offline" mode enabled.
- Network/IP change so the PC can't reach a network printer.
- Outdated/corrupt printer driver.
- Stuck print jobs blocking the queue.

## Diagnostics / Event Log Signals
- Settings > Bluetooth & devices > Printers & scanners shows "Offline".
- System log: PrintService events; spooler crashes.
- Ping the printer's IP to confirm reachability.

## Recommended Fixes (require user confirmation)
1. Power-cycle the printer; check cables/Wi-Fi and that it has paper/ink and no error lights.
2. Turn off offline mode: Printers & scanners > printer > Open print queue > Printer menu > untick "Use Printer Offline".
3. Clear the queue and restart the spooler: `services.msc` > Print Spooler > Stop; delete files in `C:\Windows\System32\spool\PRINTERS`; Start the spooler.
4. Run the printer troubleshooter: Settings > System > Troubleshoot > Other troubleshooters > Printer.
5. For network printers, confirm the IP (print a config page) and re-add by IP if it changed.
6. Update/reinstall the printer driver from the manufacturer; remove and re-add the printer.
7. Set the correct printer as Default and disable "Let Windows manage my default printer" if it keeps switching.

## Prevention
- Use a static IP/reservation for network printers.
- Keep printer firmware and drivers updated.
