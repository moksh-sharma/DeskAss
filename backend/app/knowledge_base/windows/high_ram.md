# High RAM / Memory Usage

## Symptoms
- "Your computer is low on memory" warnings.
- Apps crash or freeze; heavy disk activity (paging).
- RAM usage stays high and grows over time (memory leak).

## Common Root Causes
- Too many applications/browser tabs open simultaneously.
- Memory leak in a long-running application (Outlook, Teams, Chrome).
- Insufficient physical RAM for the workload.
- Large files or VMs loaded in memory.

## Diagnostics To Check
- RAM usage > 85% with low available GB.
- Identify top memory process from top_memory_processes.
- Correlate growth with uptime (leak) vs many apps (load).

## Recommended Fixes (require user confirmation)
1. Close unused applications and browser tabs.
2. Restart the leaking application (commonly Outlook/Teams/Chrome).
3. Restart the PC if uptime is high to clear leaks.
4. Increase virtual memory (page file) as a temporary measure.
5. Consider a RAM upgrade for chronic pressure.

## Prevention
- Restart memory-heavy apps periodically.
- Use browser tab suspender extensions.
- Match RAM to workload (16GB+ for heavy multitasking).
