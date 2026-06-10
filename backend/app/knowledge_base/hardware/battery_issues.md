# Laptop Battery and Charging Problems

## Symptoms
- Battery drains very fast or won't hold charge.
- "Plugged in, not charging" or charges very slowly.
- Laptop only runs when plugged in; dies instantly on battery.
- Battery percentage jumps or is stuck.

## Common Root Causes
- Worn-out battery (high cycle count, degraded capacity).
- Faulty charger, cable, or charging port.
- Power/battery driver issues (ACPI, "Microsoft ACPI-Compliant Control Method Battery").
- Aggressive power settings or background apps draining charge.
- BIOS/firmware power management bug.

## Diagnostics / Event Log Signals
- `powercfg /batteryreport` shows design capacity vs full charge capacity (health) and cycle count.
- `powercfg /energy` reports power efficiency problems.
- Battery icon shows "X% available (plugged in, not charging)".

## Recommended Fixes (require user confirmation)
1. Generate a battery report: run `powercfg /batteryreport` and compare Full Charge Capacity to Design Capacity (large drop = worn battery).
2. Try a different known-good charger and cable; inspect the port for debris/damage.
3. Reinstall the battery driver: Device Manager > Batteries > uninstall "Microsoft ACPI-Compliant Control Method Battery" > scan for hardware changes (do not remove the ACPI battery if it won't reinstall).
4. Update BIOS/UEFI and chipset drivers from the manufacturer.
5. Review battery drain: Settings > System > Power & battery > Battery usage to find heavy apps.
6. Set a balanced power plan; lower screen brightness and disable background apps.
7. If capacity is badly degraded, replace the battery.

## Prevention
- Avoid constant 100% charge and deep discharges; keep firmware updated.
- Use the manufacturer's charger.
