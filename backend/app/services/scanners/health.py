"""Machine health report: derive a 0-100 score per category + overall status."""
from __future__ import annotations

from typing import Any


def _clamp(v: float) -> int:
    return int(max(0, min(100, round(v))))


def _status(score: int) -> str:
    if score >= 80:
        return "Healthy"
    if score >= 50:
        return "Warning"
    return "Critical"


def _cpu_health(hardware: dict, performance: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    usage = (performance.get("cpu") or {}).get("average_pct")
    if usage is None:
        usage = (hardware.get("cpu") or {}).get("current_usage_pct")
    if usage is not None:
        if usage >= 90:
            score -= 45; notes.append(f"CPU sustained at {usage}%.")
        elif usage >= 75:
            score -= 25; notes.append(f"CPU elevated at {usage}%.")
    temp = (hardware.get("cpu") or {}).get("temperature_c")
    if temp and temp >= 90:
        score -= 20; notes.append(f"CPU temperature high ({temp}°C).")
    return _clamp(score), notes


def _memory_health(performance: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    usage = (performance.get("memory") or {}).get("current_pct")
    if usage is not None:
        if usage >= 92:
            score -= 45; notes.append(f"Memory critically high ({usage}%).")
        elif usage >= 80:
            score -= 25; notes.append(f"Memory usage high ({usage}%).")
    return _clamp(score), notes


def _disk_health(hardware: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    for d in (hardware.get("storage") or {}).get("logical_drives", []):
        pct = d.get("usage_pct")
        if pct is None:
            continue
        if pct >= 95:
            score -= 30; notes.append(f"Drive {d.get('drive')} almost full ({pct}%).")
        elif pct >= 85:
            score -= 15; notes.append(f"Drive {d.get('drive')} low on space ({pct}%).")
    for d in (hardware.get("disk_health") or {}).get("disks", []):
        if (d.get("smart_health") or "").lower() not in ("healthy", "", "none"):
            score -= 40; notes.append(f"Disk '{d.get('name')}' SMART status: {d.get('smart_health')}.")
    return _clamp(score), notes


def _network_health(network: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    conn = network.get("connectivity") or {}
    if conn.get("internet") is False:
        score -= 50; notes.append("No internet connectivity.")
    if conn.get("dns_resolution") is False:
        score -= 30; notes.append("DNS resolution failing.")
    lat = conn.get("internet_latency_ms")
    if lat and lat >= 300:
        score -= 10; notes.append(f"High latency ({lat} ms).")
    return _clamp(score), notes


def _security_health(security: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    if not security.get("available", True):
        return 100, notes
    if security.get("disabled_protection"):
        score -= 45; notes.append("No active antivirus / real-time protection.")
    fw = security.get("firewall") or {}
    if fw.get("all_enabled") is False:
        score -= 20; notes.append("One or more firewall profiles are disabled.")
    if not (security.get("bitlocker") or {}).get("system_drive_protected"):
        score -= 5; notes.append("System drive is not encrypted (BitLocker off).")

    defender = security.get("windows_defender") or {}
    sig_age = defender.get("signature_age_days")
    if isinstance(sig_age, (int, float)) and sig_age > 7:
        score -= 10; notes.append(f"Antivirus signatures are {int(sig_age)} days old.")

    if (security.get("uac") or {}).get("enabled") is False:
        score -= 15; notes.append("User Account Control (UAC) is disabled.")

    remote = security.get("remote_access") or {}
    if remote.get("smb1_enabled") is True:
        score -= 15; notes.append("Legacy SMBv1 protocol is enabled (known attack vector).")

    accounts = security.get("local_accounts") or {}
    if accounts.get("guest_account_enabled"):
        score -= 10; notes.append("Guest account is enabled.")
    no_pwd = accounts.get("accounts_without_password") or []
    if no_pwd:
        score -= 10; notes.append(f"{len(no_pwd)} enabled account(s) without a password.")

    if (security.get("secure_boot") or {}).get("enabled") is False:
        score -= 5; notes.append("Secure Boot is disabled.")
    tpm = security.get("tpm") or {}
    if tpm.get("available") and tpm.get("present") and tpm.get("ready") is False:
        score -= 5; notes.append("TPM is present but not ready.")
    return _clamp(score), notes


def _os_health(operating_system: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    activation = operating_system.get("activation") or {}
    if activation.get("available") and activation.get("activated") is False:
        score -= 15; notes.append(f"Windows is not activated ({activation.get('status') or 'unlicensed'}).")
    reboot = operating_system.get("pending_reboot") or {}
    if reboot.get("required"):
        score -= 10; notes.append("A system reboot is pending (updates/servicing waiting on restart).")
    updates = operating_system.get("updates") or {}
    pending = updates.get("pending_count")
    if isinstance(pending, (int, float)) and pending >= 10:
        score -= 15; notes.append(f"{int(pending)} Windows updates are pending.")
    elif isinstance(pending, (int, float)) and pending >= 1:
        score -= 5; notes.append(f"{int(pending)} Windows update(s) pending.")
    uptime = (operating_system.get("windows") or {}).get("uptime_hours")
    if isinstance(uptime, (int, float)) and uptime >= 24 * 14:
        score -= 10; notes.append(f"Machine has not rebooted for {round(uptime / 24)} days.")
    return _clamp(score), notes


def _device_health(hardware: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    devices = hardware.get("devices") or {}
    problems = devices.get("problem_devices") or []
    if problems:
        score -= min(60, 20 * len(problems))
        names = ", ".join(d.get("name") for d in problems[:3] if d.get("name"))
        notes.append(f"{len(problems)} device(s) reporting errors: {names}.")
    return _clamp(score), notes


def _app_health(crash: dict, services: dict, startup: dict) -> tuple[int, list[str]]:
    notes: list[str] = []
    score = 100
    summary = (crash or {}).get("summary") or {}
    if summary.get("bsod_count"):
        score -= 30; notes.append(f"{summary['bsod_count']} blue-screen/shutdown event(s) recently.")
    if summary.get("crash_count", 0) >= 5:
        score -= 20; notes.append(f"{summary['crash_count']} app crashes in the last 7 days.")
    failed = (services or {}).get("failed_critical") or []
    if failed:
        score -= 20; notes.append(f"{len(failed)} critical service(s) not running.")
    high = (startup or {}).get("high_impact_count", 0)
    if high >= 5:
        score -= 10; notes.append(f"{high} high-impact startup programs.")
    return _clamp(score), notes


def _combine(scores: list[int]) -> int:
    """Average the sub-scores but let the worst one drag the result down."""
    if not scores:
        return 100
    avg = sum(scores) / len(scores)
    return _clamp(min(avg, min(scores) + 10))


def build_health_report(sections: dict[str, Any]) -> dict:
    """Reduce all scanner sections into two top-level scores: hardware + software."""
    hardware = sections.get("hardware") or {}
    performance = sections.get("performance") or {}
    network = sections.get("network") or {}
    security = sections.get("security") or {}
    crash = sections.get("crash_analysis") or {}
    services = sections.get("services") or {}
    startup = sections.get("startup_programs") or {}
    operating_system = sections.get("operating_system") or {}

    # Hardware = CPU, memory, disks/SMART, physical devices.
    cpu_s, cpu_n = _cpu_health(hardware, performance)
    mem_s, mem_n = _memory_health(performance)
    disk_s, disk_n = _disk_health(hardware)
    dev_s, dev_n = _device_health(hardware)
    hw_score = _combine([cpu_s, mem_s, disk_s, dev_s])
    hw_notes = cpu_n + mem_n + disk_n + dev_n

    # Software = security posture, OS state, app/system stability, networking.
    sec_s, sec_n = _security_health(security)
    os_s, os_n = _os_health(operating_system)
    app_s, app_n = _app_health(crash, services, startup)
    net_s, net_n = _network_health(network)
    sw_score = _combine([sec_s, os_s, app_s, net_s])
    sw_notes = sec_n + os_n + app_n + net_n

    categories = {
        "hardware": {"score": hw_score, "status": _status(hw_score), "notes": hw_notes},
        "software": {"score": sw_score, "status": _status(sw_score), "notes": sw_notes},
    }

    overall = _combine([hw_score, sw_score])
    recommendations = (hw_notes + sw_notes)[:10] or [
        "No significant issues detected. System looks healthy."
    ]

    return {
        "overall_score": overall,
        "overall_status": _status(overall),
        "categories": categories,
        "recommended_actions": recommendations,
    }
