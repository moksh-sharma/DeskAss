# RAM / Memory Errors

## Symptoms
- Frequent random BSODs (MEMORY_MANAGEMENT, PAGE_FAULT_IN_NONPAGED_AREA).
- Apps crash randomly; files become corrupted.
- PC fails to POST or beeps on startup (desktops).
- Less usable RAM than installed.

## Common Root Causes
- A failing or improperly seated RAM module.
- Incompatible modules or unstable XMP/overclock memory profile.
- Dust/oxidation on contacts.
- Hardware-reserved memory due to integrated graphics or a stuck module.

## Diagnostics / Event Log Signals
- Windows Memory Diagnostic results (Event Viewer > Windows Logs > System, source "MemoryDiagnostics-Results").
- MemTest86 reports errors on specific addresses.
- WHEA-Logger correctable/uncorrectable memory errors.
- Task Manager shows "Hardware reserved" memory unusually high.

## Recommended Fixes (require user confirmation)
1. Run Windows Memory Diagnostic: `mdsched.exe` > restart now; review results in Event Viewer.
2. For thorough testing, run MemTest86 from a USB stick for several passes (overnight).
3. Power off, reseat each RAM module; clean contacts with isopropyl alcohol (desktops).
4. Test one module at a time / one slot at a time to identify a faulty stick or slot.
5. Disable XMP/overclock in BIOS to test at stock speeds; ensure modules are on the QVL.
6. Update BIOS/UEFI for memory compatibility fixes.
7. Replace any module that consistently fails.

## Prevention
- Buy matched, compatible memory kits.
- Avoid aggressive memory overclocks on work machines.
