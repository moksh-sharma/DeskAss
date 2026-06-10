# Sleep, Hibernate, and Wake Problems

## Symptoms
- PC won't go to sleep, or wakes up immediately on its own.
- Black screen on wake; must hold power button to recover.
- Laptop drains battery while "asleep"; runs hot in the bag.

## Common Root Causes
- Devices (mouse, keyboard, network adapter) allowed to wake the PC.
- Scheduled tasks or wake timers.
- Modern Standby (S0) behaving poorly with certain drivers.
- Outdated GPU/chipset drivers; fast startup conflicts.

## Diagnostics / Event Log Signals
- `powercfg /lastwake` shows what woke the system.
- `powercfg /requests` shows what is preventing sleep.
- `powercfg /sleepstudy` (Modern Standby) report shows drain sources.
- System log: Power-Troubleshooter Event ID 1 with wake source.

## Recommended Fixes (require user confirmation)
1. Identify the wake source with `powercfg /lastwake` and `powercfg /devicequery wake_armed`.
2. Stop a device from waking: Device Manager > device > Properties > Power Management > untick "Allow this device to wake the computer".
3. Disable wake timers: Power Options > Change plan settings > Advanced > Sleep > Allow wake timers > Disable.
4. Update GPU and chipset drivers.
5. Disable fast startup if wake shows a black screen: Control Panel > Power Options > Choose what the power buttons do.
6. For battery drain on Modern Standby laptops, review `powercfg /sleepstudy` and update firmware/drivers.

## Prevention
- Keep firmware (BIOS/UEFI) and drivers updated.
- Limit which devices can wake the PC.
