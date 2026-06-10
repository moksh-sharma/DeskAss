# Slow Internet / Network Performance

## Symptoms
- Web pages and downloads are slow despite a good plan.
- High latency in calls/games; buffering video.
- One device is slow while others are fine, or all are slow.

## Common Root Causes
- Weak Wi-Fi signal, congestion, or 2.4 GHz interference.
- Bandwidth hogs (updates, cloud sync, downloads) on the PC or network.
- Outdated NIC/Wi-Fi driver or router firmware.
- ISP throttling/outage; DNS resolution delays.
- Background malware.

## Diagnostics / Event Log Signals
- Speed test shows far below the plan; high ping/jitter.
- Task Manager > Performance/Networking and Resource Monitor show which process uses bandwidth.
- Wi-Fi signal strength low; many networks on the same channel.

## Recommended Fixes (require user confirmation)
1. Run a speed test wired vs Wi-Fi to localize the bottleneck.
2. In Task Manager and Resource Monitor, find apps consuming bandwidth (OneDrive, Windows Update, Steam) and pause them.
3. Improve Wi-Fi: move closer to the router, switch to 5 GHz, change the router channel, reduce interference.
4. Update Wi-Fi/NIC drivers and router firmware.
5. Set a fast DNS (e.g. 1.1.1.1 or 8.8.8.8) and flush DNS: `ipconfig /flushdns`.
6. Reset the network stack if performance is erratic: `netsh winsock reset`, `netsh int ip reset`.
7. Scan for malware that may use bandwidth.

## Prevention
- Prefer 5 GHz/wired for heavy use.
- Schedule large updates/backups off-hours.
