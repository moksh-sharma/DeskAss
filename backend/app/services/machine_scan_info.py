"""Informational fact responder.

The troubleshooter is fault-oriented (it answers when something is wrong). Many
user questions are purely factual ("What CPU do I have?", "Is antivirus enabled?",
"What is my IP address?"). This module answers those directly from the scan data,
returning Severity.info findings even when nothing is wrong.

It only fires for clearly informational questions (so it never adds noise to a
"why is X broken" troubleshooting answer), and each topic reads the relevant
scan section defensively - missing fields are simply omitted.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app.models.schemas import IssueProfile, InventoryItem, Severity, TroubleshooterFinding
from app.services.question_intent import (
    TROUBLE_RE,
    _FAILURE_INVENTORY_RE,
    _LIST_INVENTORY_RE,
    classify_query_intent,
    is_scan_only_intent,
)


def is_info_question(message: str) -> bool:
    """Backward-compatible: True for informational or inventory questions."""
    return is_scan_only_intent(classify_query_intent(message))


def is_printer_inventory_question(message: str) -> bool:
    """Printer questions that should skip fault handlers (status / inventory)."""
    msg = message or ""
    if TROUBLE_RE.search(msg):
        return False
    if not re.search(r"\bprinter", msg, re.I):
        return False
    return is_scan_only_intent(classify_query_intent(msg))


def is_printer_connection_question(message: str) -> bool:
    """True when the user asks whether a printer is connected (not LAN inventory)."""
    msg = message or ""
    return bool(
        re.search(
            r"\b(?:connected\s+to\s+(?:any\s+)?printers?|"
            r"(?:is|are)\s+(?:my\s+)?(?:laptop|pc|computer|machine)?\s*"
            r"(?:connected\s+to\s+)?(?:any\s+)?printers?|"
            r"any\s+printers?\s+connected|printers?\s+connected)\b",
            msg,
            re.I,
        )
    )


def _fact(fid: str, title: str, area: str, detected: str,
          steps: list[str] | None = None, prompt: str = "",
          severity: Severity = Severity.info,
          inventory_items: list[InventoryItem] | None = None) -> TroubleshooterFinding:
    return TroubleshooterFinding(
        id=f"info_{fid}",
        title=title,
        area=area,
        severity=severity,
        detected=detected,
        likely_cause=detected,
        resolution_steps=steps or [],
        inventory_items=inventory_items or [],
        ask_ai_prompt=prompt or title,
    )


def _yn(v: Any) -> str:
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    return "Unknown"


# --------------------------------------------------------------------------- #
#  Topic builders. Each returns a finding or None.
# --------------------------------------------------------------------------- #
def _cpu(hw, sw, msg):
    cpu = hw.get("cpu") or {}
    if not cpu:
        return None
    parts = [f"CPU: {cpu.get('processor_name')}"]
    if cpu.get("manufacturer"):
        parts.append(f"by {cpu.get('manufacturer')}")
    cores = cpu.get("physical_cores"); threads = cpu.get("logical_cores")
    if cores or threads:
        parts.append(f"{cores} cores / {threads} threads")
    if cpu.get("max_frequency_mhz"):
        parts.append(f"up to {round(cpu['max_frequency_mhz']/1000, 2)} GHz")
    if cpu.get("architecture"):
        parts.append(str(cpu["architecture"]))
    detail = ", ".join(str(p) for p in parts) + "."
    if cpu.get("current_usage_pct") is not None:
        detail += f" Current load {cpu['current_usage_pct']}%."
    return _fact("cpu", "Processor (CPU)", "Hardware", detail,
                 prompt="What CPU do I have and is it fast enough?")


_IDLE_PROCESS_RE = re.compile(r"system\s+idle|idle\s+process", re.I)
_TOP_CPU_QUESTION_RE = re.compile(
    r"\b(?:"
    r"which\s+(?:app|application|process|program).{0,50}?(?:cpu|processor)|"
    r"which\s+(?:app|application|process|program).{0,50}?(?:most|more).{0,20}?(?:cpu|processor)|"
    r"what\s+(?:app|application|process|program).{0,50}?(?:cpu|processor|most\s+cpu|more\s+cpu)|"
    r"(?:app|application|process|program).{0,40}?(?:using|uses|consumes).{0,25}?(?:most|more).{0,20}?(?:cpu|processor)|"
    r"(?:most|highest|top).{0,25}?(?:cpu|processor).{0,40}(?:app|application|process|program)|"
    r"who\s+is\s+using\s+(?:the\s+)?(?:most|more)\s+cpu"
    r")\b",
    re.I,
)
_TOP_RAM_QUESTION_RE = re.compile(
    r"\b(?:"
    r"which\s+(?:app|application|process|program).{0,50}?(?:ram|memory)|"
    r"which\s+(?:app|application|process|program).{0,50}?(?:most|more).{0,20}?(?:ram|memory)|"
    r"what\s+(?:app|application|process|program).{0,50}?(?:ram|memory|most\s+ram|more\s+ram)|"
    r"(?:app|application|process|program).{0,40}?(?:using|uses|consumes).{0,25}?(?:most|more).{0,20}?(?:ram|memory)|"
    r"(?:most|highest|top).{0,25}?(?:ram|memory).{0,40}(?:app|application|process|program)|"
    r"who\s+is\s+using\s+(?:the\s+)?(?:most|more)\s+(?:ram|memory)"
    r")\b",
    re.I,
)


def is_top_cpu_question(message: str) -> bool:
    """True when the user asks which application/process uses the most CPU."""
    text = message or ""
    return bool(_TOP_CPU_QUESTION_RE.search(text)) and not bool(_TOP_RAM_QUESTION_RE.search(text))


def is_top_ram_question(message: str) -> bool:
    """True when the user asks which application/process uses the most RAM."""
    text = message or ""
    return bool(_TOP_RAM_QUESTION_RE.search(text)) and not bool(_TOP_CPU_QUESTION_RE.search(text))


def _friendly_proc_name(name: str) -> str:
    label = (name or "process").strip()
    if label.lower().endswith(".exe"):
        label = label[:-4]
    return label or "process"


def _fmt_mem_mb(mb: float | int | None) -> str:
    mb = mb or 0
    if mb >= 1024:
        return f"{round(mb / 1024, 2)} GB"
    return f"{round(mb, 1)} MB"


def _process_source_rows(proc_section: dict) -> list[dict]:
    """Prefer the full process table; otherwise merge top_cpu/top_memory lists."""
    all_p = proc_section.get("all_processes")
    if all_p:
        return list(all_p)
    by_key: dict[Any, dict] = {}
    for key in ("top_cpu", "top_memory"):
        for p in proc_section.get(key) or []:
            pid = p.get("pid")
            k = pid if pid is not None else (p.get("name"), p.get("memory_mb"), p.get("cpu_pct"))
            if k not in by_key:
                by_key[k] = dict(p)
            else:
                cur = by_key[k]
                cur["cpu_pct"] = max(cur.get("cpu_pct") or 0, p.get("cpu_pct") or 0)
                cur["memory_mb"] = max(cur.get("memory_mb") or 0, p.get("memory_mb") or 0)
    return list(by_key.values())


def _aggregate_by_process_name(rows: list[dict]) -> list[dict]:
    """Sum CPU/RAM for multiple instances of the same executable name."""
    buckets: dict[str, dict] = {}
    for p in rows:
        name = _friendly_proc_name(p.get("name") or "?")
        key = name.lower()
        if key not in buckets:
            buckets[key] = {"name": name, "cpu_pct": 0.0, "memory_mb": 0.0, "instances": 0}
        b = buckets[key]
        b["cpu_pct"] += float(p.get("cpu_pct") or 0)
        b["memory_mb"] += float(p.get("memory_mb") or 0)
        b["instances"] += 1
    out: list[dict] = []
    for b in buckets.values():
        b["cpu_pct"] = round(b["cpu_pct"], 1)
        b["memory_mb"] = round(b["memory_mb"], 1)
        out.append(b)
    return out


def pick_top_cpu_processes(proc_section: dict, *, limit: int = 5) -> list[dict]:
    """Return real CPU consumers, skipping System Idle Process."""
    ranked = sorted(
        _aggregate_by_process_name(_process_source_rows(proc_section)),
        key=lambda p: p.get("cpu_pct") or 0,
        reverse=True,
    )
    out: list[dict] = []
    for p in ranked:
        name = p.get("name") or ""
        if _IDLE_PROCESS_RE.search(name):
            continue
        if (p.get("cpu_pct") or 0) <= 0:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def pick_top_memory_processes(proc_section: dict, *, limit: int = 5) -> list[dict]:
    """Return processes using the most RAM."""
    ranked = sorted(
        _aggregate_by_process_name(_process_source_rows(proc_section)),
        key=lambda p: p.get("memory_mb") or 0,
        reverse=True,
    )
    out: list[dict] = []
    for p in ranked:
        if (p.get("memory_mb") or 0) <= 0:
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _top_cpu_application(hw, sw, msg):
    proc = sw.get("running_processes") or {}
    top = pick_top_cpu_processes(proc, limit=5)
    cpu = hw.get("cpu") or {}
    cpu_now = cpu.get("current_usage_pct")

    if not top:
        detail = "No application with measurable CPU usage was detected in the live process list."
        if cpu_now is not None:
            detail += f" Overall CPU load is {cpu_now}%."
        return _fact(
            "top_cpu_app",
            "Top CPU Application",
            "Performance",
            detail,
            prompt="Which application is using the most CPU?",
        )

    leader = top[0]
    name = _friendly_proc_name(leader.get("name") or "process")
    pct = leader.get("cpu_pct")
    mem = leader.get("memory_mb")
    instances = leader.get("instances") or 1
    detail = f"{name} is using the most CPU right now at {pct}%."
    if instances > 1:
        detail += f" ({instances} processes combined.)"
    if mem:
        detail += f" It is using {_fmt_mem_mb(mem)} RAM."
    if cpu_now is not None:
        detail += f" Overall CPU load is {cpu_now}%."
    if len(top) > 1:
        also = ", ".join(
            f"{_friendly_proc_name(p.get('name') or '?')} ({p.get('cpu_pct')}% CPU)"
            for p in top[1:4]
        )
        detail += f" Also high: {also}."

    sev = Severity.warning if (pct or 0) >= 50 or (cpu_now or 0) >= 85 else Severity.info
    return _fact(
        "top_cpu_app",
        "Top CPU Application",
        "Performance",
        detail,
        severity=sev,
        prompt="Which application is using the most CPU?",
    )


def _top_ram_application(hw, sw, msg):
    proc = sw.get("running_processes") or {}
    top = pick_top_memory_processes(proc, limit=5)
    ram = hw.get("ram") or {}
    ram_pct = ram.get("utilization_pct")
    ram_used = ram.get("used_gb")
    ram_total = ram.get("total_gb")

    if not top:
        detail = "No application with measurable memory usage was detected in the live process list."
        if ram_pct is not None:
            detail += f" Overall RAM usage is {ram_pct}%."
        return _fact(
            "top_ram_app",
            "Top RAM Application",
            "Performance",
            detail,
            prompt="Which application is using the most RAM?",
        )

    leader = top[0]
    name = _friendly_proc_name(leader.get("name") or "process")
    mem = leader.get("memory_mb")
    cpu = leader.get("cpu_pct")
    instances = leader.get("instances") or 1
    detail = f"{name} is using the most RAM right now at {_fmt_mem_mb(mem)}."
    if instances > 1:
        detail += f" ({instances} processes combined.)"
    if cpu:
        detail += f" It is using {cpu}% CPU."
    if ram_pct is not None:
        detail += f" Overall RAM usage is {ram_pct}%"
        if ram_used is not None and ram_total is not None:
            detail += f" ({ram_used} GB used of {ram_total} GB)"
        detail += "."
    if len(top) > 1:
        also = ", ".join(
            f"{_friendly_proc_name(p.get('name') or '?')} ({_fmt_mem_mb(p.get('memory_mb'))})"
            for p in top[1:4]
        )
        detail += f" Also high: {also}."

    sev = Severity.warning if (mem or 0) >= 1500 or (ram_pct or 0) >= 85 else Severity.info
    return _fact(
        "top_ram_app",
        "Top RAM Application",
        "Performance",
        detail,
        severity=sev,
        prompt="Which application is using the most RAM?",
    )


def _gpu(hw, sw, msg):
    gpus = (hw.get("gpu") or {}).get("gpus") or []
    if not gpus:
        return None
    lines = []
    for g in gpus[:4]:
        bit = g.get("model") or "GPU"
        extra = []
        if g.get("vram_gb"):
            extra.append(f"{g['vram_gb']} GB VRAM")
        if g.get("driver_version"):
            extra.append(f"driver {g['driver_version']}")
        if g.get("driver_date"):
            extra.append(f"dated {g['driver_date']}")
        if extra:
            bit += f" ({', '.join(extra)})"
        lines.append(bit)
    return _fact("gpu", "Graphics (GPU)", "Hardware",
                 "Graphics adapter(s): " + "; ".join(lines) + ".",
                 prompt="What GPU do I have?")


def _ram(hw, sw, msg):
    ram = hw.get("ram") or {}
    if not ram:
        return None
    detail = (f"RAM: {ram.get('total_gb')} GB total, "
              f"{ram.get('available_gb')} GB available "
              f"({ram.get('utilization_pct')}% in use).")
    mods = ram.get("modules") or []
    used_slots = ram.get("module_count") or len(mods)
    total_slots = ram.get("slots_total")
    if total_slots is not None:
        free_slots = total_slots - (used_slots or 0)
        detail += f" {used_slots} of {total_slots} slots populated ({free_slots} free)."
    if mods:
        spec = mods[0]
        mb = []
        if spec.get("type"):
            mb.append(spec["type"])
        if spec.get("speed_mhz"):
            mb.append(f"{spec['speed_mhz']} MHz")
        if spec.get("manufacturer"):
            mb.append(spec["manufacturer"])
        if mb:
            detail += f" Modules: {', '.join(str(x) for x in mb)}."
    steps: list[str] = []
    if total_slots and (total_slots - (used_slots or 0)) > 0:
        steps = [f"You have {total_slots - used_slots} free RAM slot(s) - RAM can be added.",
                 "Match the existing module type/speed for best compatibility."]
    return _fact("ram", "Memory (RAM)", "Hardware", detail, steps=steps,
                 prompt="How much RAM do I have and can I upgrade it?")


def _motherboard(hw, sw, msg):
    mb = hw.get("motherboard") or {}
    sysd = hw.get("system") or {}
    if not mb and not sysd:
        return None
    parts = []
    if mb.get("manufacturer") or mb.get("model"):
        parts.append(f"Motherboard: {mb.get('manufacturer') or ''} {mb.get('model') or ''}".strip())
    if mb.get("bios_version"):
        parts.append(f"BIOS {mb['bios_version']}" + (f" ({mb.get('bios_release_date')})" if mb.get("bios_release_date") else ""))
    if sysd.get("manufacturer") or sysd.get("model"):
        parts.append(f"System: {sysd.get('manufacturer') or ''} {sysd.get('model') or ''}".strip())
    if not parts:
        return None
    return _fact("motherboard", "Motherboard & BIOS", "Hardware", ". ".join(parts) + ".",
                 prompt="What motherboard and BIOS do I have?")


def _serial(hw, sw, msg):
    sysd = hw.get("system") or {}
    if not sysd:
        return None
    parts = []
    if sysd.get("serial_number"):
        parts.append(f"Serial/Service tag: {sysd['serial_number']}")
    if sysd.get("manufacturer") or sysd.get("model"):
        parts.append(f"{sysd.get('manufacturer') or ''} {sysd.get('model') or ''}".strip())
    if sysd.get("asset_tag"):
        parts.append(f"Asset tag: {sysd['asset_tag']}")
    if sysd.get("chassis_type"):
        parts.append(f"Chassis: {sysd['chassis_type']}")
    if not parts:
        return None
    return _fact("serial", "Machine Identity", "Hardware", ". ".join(parts) + ".",
                 prompt="What is the serial number / model of my machine?")


_LARGEST_FILE_QUESTION_RE = re.compile(
    r"\b(?:"
    r"which\s+file|what\s+file|biggest\s+file|largest\s+file|"
    r"file\s+(?:taking|using|consuming).{0,40}(?:most|more)\s+space|"
    r"(?:which|what)\s+(?:file|folder).{0,40}(?:most|more)\s+space|"
    r"taking\s+(?:the\s+)?(?:most|more)\s+space|"
    r"what(?:'s| is)\s+using\s+(?:the\s+)?(?:most|more)\s+space|"
    r"using\s+(?:the\s+)?(?:most|more)\s+space\s+on"
    r")\b",
    re.I,
)


def is_largest_file_question(message: str) -> bool:
    """True when the user asks which file or folder uses the most disk space."""
    return bool(_LARGEST_FILE_QUESTION_RE.search(message or ""))


def _storage_scan_data(sw: dict) -> dict | None:
    deep = sw.get("storage_deep") or {}
    if deep and not deep.get("error"):
        return deep
    quick = sw.get("storage_intelligence") or {}
    if quick and not quick.get("error"):
        return quick
    return None


def _largest_file(hw, sw, msg, report: dict | None = None):
    """Answer which individual file uses the most space from a storage walk."""
    sw = sw or {}
    if report and report.get("software"):
        sw = {**sw, **(report.get("software") or {})}
    data = _storage_scan_data(sw)
    tree = (data or {}).get("tree") or {}
    top_files = tree.get("top_files") or []
    top_folders = tree.get("top_folders") or []
    drive = (data or {}).get("scanned_drive") or ""
    drive_note = f" on {drive}" if drive else ""

    asks_folder = bool(re.search(r"\bfolder\b", msg or "", re.I)) and not re.search(
        r"\bfile\b", msg or "", re.I
    )

    if asks_folder and top_folders:
        leader = top_folders[0]
        path = leader.get("path") or "unknown folder"
        size = leader.get("size_gb")
        detail = f"{path} is the largest folder{drive_note} at {size} GB."
        if len(top_folders) > 1:
            also = ", ".join(
                f"{f.get('path')} ({f.get('size_gb')} GB)" for f in top_folders[1:4] if f.get("path")
            )
            detail += f" Also large: {also}."
        return _fact(
            "largest_folder",
            f"Largest Folder{drive_note}",
            "Storage",
            detail,
            steps=[
                f"Open {path} in File Explorer and sort by size to see what is inside.",
                "Move or archive old projects, games, or media you no longer need.",
                "Run Disk Cleanup after removing personal files.",
            ],
            prompt="Which folder is using the most space on my PC?",
        )

    if top_files:
        leader = top_files[0]
        path = leader.get("path") or "unknown file"
        size = leader.get("size_gb")
        detail = f"The largest file{drive_note} is {path} at {size} GB."
        if len(top_files) > 1:
            also = ", ".join(
                f"{f.get('path')} ({f.get('size_gb')} GB)" for f in top_files[1:4] if f.get("path")
            )
            detail += f" Other large files: {also}."
        steps = [
            f"Review {path} — move it to external storage or delete if you no longer need it.",
            "Check Downloads and old video or installer files.",
            "Empty the Recycle Bin after deleting files.",
        ]
        if tree.get("truncated"):
            detail += " (Scan was time-limited; larger files may exist outside scanned paths.)"
        return _fact(
            "largest_file",
            f"Largest File{drive_note}",
            "Storage",
            detail,
            steps=steps,
            prompt="Which file is using the most space on my laptop?",
        )

    if top_folders and not asks_folder:
        leader = top_folders[0]
        detail = (
            f"No single large file was ranked yet, but the largest folder{drive_note} is "
            f"{leader.get('path')} ({leader.get('size_gb')} GB). "
            "Open it and sort by size to find the biggest file inside."
        )
        return _fact(
            "largest_file",
            f"Largest File{drive_note}",
            "Storage",
            detail,
            prompt="Which file is using the most space on my laptop?",
        )

    if not data:
        return _fact(
            "largest_file",
            "Largest File",
            "Storage",
            "Could not scan disk usage — storage intelligence did not complete.",
            prompt="Which file is using the most space on my laptop?",
        )

    return _fact(
        "largest_file",
        "Largest File",
        "Storage",
        "A deep disk walk did not find any large individual files in the scanned paths. "
        "Try specifying a drive (e.g. C: or D:) or run a full storage scan.",
        prompt="Which file is using the most space on my laptop?",
    )


def _storage(hw, sw, msg):
    st = hw.get("storage") or {}
    disks = st.get("physical_disks") or []
    logical = st.get("logical_drives") or []
    if not disks and not logical:
        return None
    dparts = []
    for d in disks[:5]:
        bit = f"{d.get('model') or d.get('name') or 'Disk'} ({d.get('media_type')}/{d.get('bus_type')}, {d.get('size_gb')} GB)"
        dparts.append(bit)
    detail = "Physical disks: " + "; ".join(dparts) + "." if dparts else ""
    if logical:
        lparts = [f"{l.get('drive')} {l.get('free_gb')} GB free of {l.get('total_gb')} GB ({l.get('usage_pct')}% used)" for l in logical[:6]]
        detail += " Volumes: " + "; ".join(lparts) + "."
    return _fact("storage_devices", "Storage Devices", "Hardware", detail.strip(),
                 prompt="What storage devices are connected and how full are they?")


def _ssd_health(hw, sw, msg):
    disks = (hw.get("disk_health") or {}).get("disks") or []
    if not disks:
        return None
    lines = []
    worst_ok = True
    for d in disks[:5]:
        smart = d.get("smart_health") or "Unknown"
        if str(smart).lower() not in ("healthy", "ok", "good", "unknown"):
            worst_ok = False
        bit = f"{d.get('name') or 'Disk'}: SMART {smart}"
        if d.get("wear_pct") is not None:
            bit += f", {d['wear_pct']}% wear"
        if d.get("temperature_c") is not None:
            bit += f", {d['temperature_c']}°C"
        if d.get("power_on_hours") is not None:
            bit += f", {d['power_on_hours']}h powered on"
        if (d.get("read_errors") or 0) or (d.get("write_errors") or 0):
            bit += f", {d.get('read_errors',0)} read/{d.get('write_errors',0)} write errors"
        lines.append(bit)
    sev = Severity.info if worst_ok else Severity.warning
    steps = ["Disk health looks normal - no action needed."] if worst_ok else [
        "Back up important data now.", "Run 'chkdsk' and monitor SMART status; plan a replacement."]
    return _fact("ssd_health", "Disk / SSD Health", "Hardware", "; ".join(lines) + ".",
                 steps=steps, prompt="How healthy are my disks?", severity=sev)


def _battery(hw, sw, msg):
    bat = hw.get("battery") or {}
    if not bat or bat.get("present") is False:
        return _fact("battery", "Battery", "Hardware",
                     "No battery detected - this looks like a desktop or the battery isn't reported.",
                     prompt="What is my battery health?")
    health = bat.get("battery_health_pct")
    detail = f"Battery at {bat.get('percentage')}% ({'charging' if bat.get('charging') else 'on battery'})."
    if health is not None:
        wear = round(100 - health, 1)
        detail += f" Health {health}% (≈{wear}% wear)."
    if bat.get("design_capacity_mwh") and bat.get("current_capacity_mwh"):
        detail += f" Capacity {bat['current_capacity_mwh']} of {bat['design_capacity_mwh']} mWh (design)."
    if bat.get("estimated_remaining"):
        detail += f" ~{bat['estimated_remaining']} remaining."
    detail += " (Windows does not expose battery charge-cycle count for most batteries.)"
    sev = Severity.info
    steps: list[str] = []
    if isinstance(health, (int, float)) and health < 60:
        sev = Severity.warning
        steps = [f"Battery health is {health}% - consider replacing the battery.",
                 "Avoid keeping it at 100% on AC constantly to slow further wear."]
    return _fact("battery", "Battery Health", "Hardware", detail, steps=steps,
                 prompt="What is my battery health and should I replace it?", severity=sev)


def _virtualization(hw, sw, msg):
    cpu = hw.get("cpu") or {}
    v = cpu.get("virtualization_firmware_enabled")
    return _fact("virtualization", "CPU Virtualization", "Hardware",
                 f"Hardware virtualization (VT-x/AMD-V) in firmware: {_yn(v)}."
                 + ("" if v else " If 'No', it can usually be enabled in BIOS/UEFI."),
                 prompt="Does my CPU support virtualization?")


def _thermal(hw, sw, msg):
    cpu = hw.get("cpu") or {}
    disks = (hw.get("disk_health") or {}).get("disks") or []
    bits = []
    ct = cpu.get("temperature_c")
    if ct is not None:
        bits.append(f"CPU {ct}°C")
    else:
        bits.append("CPU temperature not exposed by this hardware (needs a vendor sensor tool)")
    for d in disks[:3]:
        if d.get("temperature_c") is not None:
            bits.append(f"{d.get('name')} {d['temperature_c']}°C")
    hot = [b for b in bits if "°C" in b and any(int(s) >= 85 for s in re.findall(r"(\d+)°C", b))]
    sev = Severity.warning if hot else Severity.info
    return _fact("thermal", "Temperatures / Thermals", "Hardware",
                 "Temperatures: " + "; ".join(bits) + ".",
                 prompt="Are any components overheating or thermal throttling?", severity=sev)


def _usb(hw, sw, msg):
    usb = ((hw.get("external_devices") or {}).get("usb") or {})
    devs = usb.get("devices") or []
    if not devs:
        return _fact("usb", "USB Devices", "Hardware", "No external USB peripherals detected.",
                     prompt="What USB devices are connected?")
    names = ", ".join(d.get("name") for d in devs[:10] if d.get("name"))
    return _fact("usb", "USB Devices", "Hardware",
                 f"{len(devs)} USB device(s) connected: {names}.",
                 prompt="What USB devices are connected?")


def _monitors(hw, sw, msg):
    mon = ((hw.get("external_devices") or {}).get("monitors") or {})
    monitors = mon.get("monitors") or []
    if not monitors:
        return None
    lines = []
    for m in monitors[:6]:
        bit = f"{m.get('manufacturer') or ''} {m.get('model') or 'Display'}".strip()
        extra = []
        if m.get("resolution"):
            extra.append(m["resolution"])
        if m.get("refresh_rate_hz"):
            extra.append(f"{m['refresh_rate_hz']}Hz")
        if m.get("connection_type"):
            extra.append(m["connection_type"])
        if extra:
            bit += f" ({', '.join(str(x) for x in extra)})"
        lines.append(bit)
    detail = f"{len(monitors)} monitor(s): " + "; ".join(lines) + "."
    if "hdr" in (msg or "").lower():
        detail += " (HDR capability is not reported via EDID; check Settings > Display > HDR.)"
    return _fact("monitors", "Monitors / Displays", "Hardware", detail,
                 prompt="What monitors are attached?")


def _fmt_audio_dev(dev: dict, kind: str) -> str:
    name = dev.get("name") or "Audio device"
    tag = "virtual" if dev.get("is_virtual") else "physical"
    health = dev.get("health") or ("Connected" if dev.get("connected") else "Unknown")
    return f"{name} ({kind}, {tag}, {health})"


_LIST_AUDIO_DEVICES_RE = re.compile(
    r"\b(?:"
    r"(?:list|show|enumerate|tell\s+me|what|which).{0,40}?"
    r"(?:audio|sound|microphone|mic|speaker|headphone|headset).{0,25}?devices?|"
    r"(?:audio|sound|microphone|mic|speaker|headphone|headset)\s+devices?\b|"
    r"devices?\s+connected.{0,30}?(?:audio|sound|microphone|mic|speaker)|"
    r"(?:audio|sound).{0,30}?devices?\s+connected"
    r")\b",
    re.I,
)


def is_list_audio_devices_question(message: str) -> bool:
    """True when the user wants an audio endpoint inventory, not fault status."""
    msg = message or ""
    if TROUBLE_RE.search(msg):
        return False
    return bool(_LIST_AUDIO_DEVICES_RE.search(msg))


def _list_audio_devices(hw, sw, msg):
    section = ((hw.get("external_devices") or {}).get("audio")) or {}
    inputs = section.get("input_devices") or []
    outputs = section.get("output_devices") or []
    all_devs = [(d, "Input") for d in inputs] + [(d, "Output") for d in outputs]

    if not all_devs:
        return _fact(
            "audio_device_list",
            "Audio Devices",
            "Audio",
            "0 audio input/output endpoint(s) found.",
            prompt="What audio devices are connected?",
        )

    items: list[InventoryItem] = []
    for dev, direction in all_devs:
        kind = "Virtual" if dev.get("is_virtual") else "Physical"
        health = (
            dev.get("health")
            or dev.get("status")
            or ("Connected" if dev.get("connected") or dev.get("working") else "Unknown")
        )
        items.append(InventoryItem(
            name=dev.get("name") or "Audio device",
            version=str(health),
            category=direction,
            detail=kind,
        ))

    n_in, n_out = len(inputs), len(outputs)
    detail = f"{len(all_devs)} audio endpoint(s) found ({n_in} input, {n_out} output)."
    return _fact(
        "audio_device_list",
        "Audio Devices",
        "Audio",
        detail,
        prompt="What audio devices are connected?",
        inventory_items=items,
    )


def _audio_devices(hw, sw, msg):
    if is_list_audio_devices_question(msg):
        return _list_audio_devices(hw, sw, msg)

    section = ((hw.get("external_devices") or {}).get("audio")) or {}
    inputs = section.get("input_devices") or []
    outputs = section.get("output_devices") or []

    if not inputs and not outputs:
        return _fact(
            "audio_devices",
            "Audio Devices",
            "Audio",
            "No audio input or output endpoints were detected by the scan.",
            prompt="What audio devices are connected?",
        )

    physical_in = [d for d in inputs if d.get("is_physical")]
    physical_out = [d for d in outputs if d.get("is_physical")]
    connected_in = [
        d for d in physical_in
        if d.get("connected") or d.get("working") or d.get("health") == "Connected"
    ]
    connected_out = [
        d for d in physical_out
        if d.get("connected") or d.get("working") or d.get("health") == "Connected"
    ]

    lines: list[str] = []
    for d in inputs[:10]:
        lines.append(_fmt_audio_dev(d, "input"))
    for d in outputs[:10]:
        lines.append(_fmt_audio_dev(d, "output"))

    n_phys = len(physical_in) + len(physical_out)
    n_conn = len(connected_in) + len(connected_out)
    virtual_n = (len(inputs) - len(physical_in)) + (len(outputs) - len(physical_out))

    detail = (
        f"{len(inputs)} input and {len(outputs)} output audio endpoint(s) detected. "
        f"{n_phys} physical ({n_conn} connected/active): "
        + "; ".join(lines) + "."
    )
    if virtual_n:
        detail += (
            f" {virtual_n} virtual/software audio device(s) are also listed "
            "(e.g. Voicemeeter, Stereo Mix) - these are not physical hardware."
        )
    if n_phys and not n_conn:
        detail += " No physical audio device is currently reporting as connected."

    return _fact(
        "audio_devices",
        "Audio Devices",
        "Audio",
        detail,
        prompt="What audio devices are connected?",
    )


def _bluetooth_devices(hw, sw, msg):
    section = ((hw.get("external_devices") or {}).get("bluetooth")) or {}
    devices = section.get("devices") or []
    connected = [d for d in devices if d.get("connected")]
    if not devices:
        if section.get("adapter_present"):
            adapters = ", ".join(section.get("adapter_names") or ["Bluetooth adapter"])
            detail = (
                f"Bluetooth adapter present ({adapters}) but no devices are paired or connected."
            )
        else:
            detail = "No Bluetooth adapter or paired devices were found."
        return _fact("bluetooth_devices", "Bluetooth Devices", "Bluetooth", detail,
                     prompt="What Bluetooth devices are connected?")

    lines = []
    for d in devices[:12]:
        state = "connected" if d.get("connected") else "paired, not connected"
        dtype = d.get("type") or "device"
        lines.append(f"{d.get('name')} ({dtype}, {state})")
    detail = (
        f"{len(devices)} paired Bluetooth device(s), {len(connected)} actively connected: "
        + "; ".join(lines) + "."
    )
    return _fact("bluetooth_devices", "Bluetooth Devices", "Bluetooth", detail,
                 prompt="What Bluetooth devices are connected?")


def _webcam_devices(hw, sw, msg):
    section = ((hw.get("external_devices") or {}).get("cameras")) or {}
    cameras = section.get("cameras") or []
    if not cameras:
        return _fact(
            "webcam_devices",
            "Cameras / Webcams",
            "Webcam",
            "No cameras or webcams were detected by the scan.",
            prompt="What cameras are connected?",
        )
    lines = []
    for c in cameras[:8]:
        tag = "virtual" if c.get("is_virtual") else "physical"
        state = c.get("health") or ("connected" if c.get("connected") else "unknown")
        lines.append(f"{c.get('name')} ({tag}, {state})")
    physical = [c for c in cameras if c.get("is_physical")]
    detail = (
        f"{len(cameras)} camera(s) detected ({len(physical)} physical): "
        + "; ".join(lines) + "."
    )
    return _fact("webcam_devices", "Cameras / Webcams", "Webcam", detail,
                 prompt="What cameras are connected?")


def _driver_problems(hw: dict) -> list[dict]:
    """Merge driver-scanner and hardware device problem lists."""
    sec = (hw.get("drivers") or {}) if isinstance(hw, dict) else {}
    problems = list(sec.get("problem_devices") or [])
    seen = {p.get("name") for p in problems if p.get("name")}
    for d in (hw.get("devices") or {}).get("problem_devices") or []:
        name = d.get("name")
        if name and name in seen:
            continue
        code = d.get("problem_code")
        problems.append({
            "name": name,
            "class": d.get("class") or d.get("category"),
            "status": d.get("status"),
            "problem_code": code,
            "problem": d.get("problem") or (f"Code {code}" if code else "Error"),
        })
        if name:
            seen.add(name)
    return problems


_ASK_FAILING_DRIVERS_RE = re.compile(
    r"\b(?:driver|drivers).{0,40}?(?:fail(?:ing|ed)|broken|error|problem)|"
    r"(?:fail(?:ing|ed)|broken|error|problem).{0,40}?(?:driver|drivers)|"
    r"\bwhich\s+drivers?\s+(?:are\s+)?(?:fail|broken|error|problem)|"
    r"\bwhat\s+drivers?\s+(?:are\s+)?(?:fail|broken|error|problem)",
    re.I,
)
_LIST_DRIVERS_RE = re.compile(
    r"\b(?:list|show|enumerate)\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?drivers?\b|"
    r"\b(?:list|show)\s+(?:me\s+)?(?:all\s+)?(?:installed\s+)?drivers?\b|"
    r"\bdriver\s+inventory\b|"
    r"\bwhat\s+drivers?\s+(?:are\s+)?(?:installed|on\s+(?:my|this)\s+(?:pc|computer|laptop))?\b",
    re.I,
)


def is_list_drivers_question(message: str) -> bool:
    """True when the user wants an installed-driver inventory, not fault status."""
    msg = message or ""
    if _ASK_FAILING_DRIVERS_RE.search(msg) or _FAILURE_INVENTORY_RE.search(msg):
        return False
    return bool(_LIST_DRIVERS_RE.search(msg))


def _list_drivers(hw, sw, msg):
    sec = (hw.get("drivers") or {}) if isinstance(hw, dict) else {}
    drivers = sec.get("installed_drivers") or []
    count = sec.get("installed_count") or len(drivers)
    if not drivers and not count:
        return _fact(
            "driver_list",
            "Installed Drivers",
            "Drivers",
            "No installed driver inventory was collected by the scan.",
            prompt="List all drivers",
        )
    if not drivers:
        detail = (
            f"{count} installed driver(s) were detected but the detailed list "
            "was not collected by the scan."
        )
        return _fact("driver_list", "Installed Drivers", "Drivers", detail,
                     prompt="List all drivers")
    items: list[InventoryItem] = []
    for d in drivers:
        items.append(InventoryItem(
            name=d.get("name") or "Driver",
            version=str(d.get("version") or ""),
            category=str(d.get("class") or ""),
            detail=str(d.get("manufacturer") or ""),
        ))
    total = count or len(drivers)
    detail = f"{total} installed driver(s) found."
    return _fact(
        "driver_list",
        "Installed Drivers",
        "Drivers",
        detail,
        prompt="List all drivers",
        inventory_items=items,
    )


def _driver_domain_answer(hw, sw, msg):
    if is_list_drivers_question(msg):
        return _list_drivers(hw, sw, msg)
    if _ASK_FAILING_DRIVERS_RE.search(msg or ""):
        return _failing_drivers(hw, sw, msg)
    return None


def _failing_drivers(hw, sw, msg):
    problems = _driver_problems(hw)
    if problems:
        lines = []
        for p in problems[:12]:
            label = p.get("name") or "Device"
            prob = p.get("problem") or f"code {p.get('problem_code')}"
            cls = p.get("class")
            bit = f"{label} ({prob})"
            if cls:
                bit += f" [{cls}]"
            lines.append(bit)
        detail = (
            f"{len(problems)} driver/device problem(s) detected: "
            + "; ".join(lines) + "."
        )
        steps = [
            "Open Device Manager (devmgmt.msc) and expand categories with warning icons.",
            "Right-click the device > Update driver > Search automatically.",
            "If that fails, download the driver from the device or PC manufacturer's site.",
        ]
        return _fact("failing_drivers", "Failing Drivers", "Drivers", detail, steps=steps,
                     prompt="Which drivers are failing?")
    return _fact(
        "failing_drivers",
        "Failing Drivers",
        "Drivers",
        "No drivers are currently failing. Device Manager reports no devices with driver errors.",
        prompt="Which drivers are failing?",
    )


def _health_score(hw, sw, msg):
    hr = sw.get("health_report") or {}
    if not hr:
        return None
    score = hr.get("overall_score")
    status = hr.get("overall_status")
    cats = hr.get("categories") or {}
    parts = [f"Overall machine health: {score}/100 ({status})."]
    for key in ("performance", "security", "reliability", "storage", "network", "compliance"):
        c = cats.get(key) or {}
        if c.get("score") is not None:
            parts.append(f"{key.title()} {c['score']}/100.")
    return _fact("health_score", "Machine Health Score", "Health", " ".join(parts),
                 prompt="What is my machine health score?")


def _wifi(hw, sw, msg):
    net = sw.get("network") or {}
    wifi = net.get("wifi") or {}
    if not wifi and not net.get("ip_config"):
        return None
    connected = wifi.get("connected")
    ssid = wifi.get("ssid")
    if connected is True:
        if ssid:
            detail = f"Yes - your laptop is connected to Wi-Fi network '{ssid}'."
        else:
            detail = "Yes - Wi-Fi is connected (network name was not reported by the scan)."
        extras = []
        if wifi.get("signal_pct") is not None:
            extras.append(f"signal {wifi['signal_pct']}%")
        if wifi.get("band"):
            extras.append(str(wifi["band"]))
        if wifi.get("radio_type"):
            extras.append(str(wifi["radio_type"]))
        if extras:
            detail += " " + ", ".join(extras) + "."
    elif connected is False:
        detail = "No - your laptop is not connected to Wi-Fi right now."
        if ssid:
            detail += f" A saved network '{ssid}' is visible but not active."
    else:
        detail = "Wi-Fi connection status could not be determined from the scan."
    ip = (net.get("ip_config") or {}).get("ip_address")
    if ip and connected:
        detail += f" IP address: {ip}."
    steps: list[str] = []
    if connected is False:
        steps = [
            "Settings > Network & internet > Wi-Fi: turn Wi-Fi on and select your network.",
            "Check that airplane mode is off.",
        ]
    return _fact(
        "wifi",
        "Wi-Fi Connection",
        "Network",
        detail,
        steps=steps,
        prompt="Is my laptop connected to Wi-Fi?",
    )


def _network_status(hw, sw, msg):
    net = sw.get("network") or {}
    ip = net.get("ip_config") or {}
    conn = net.get("connectivity") or {}
    wifi = net.get("wifi") or {}
    if not (ip or conn or wifi):
        return None
    parts = []
    if ip.get("ip_address"):
        parts.append(f"IP {ip['ip_address']}")
    if ip.get("interface"):
        parts.append(f"via {ip['interface']}")
    if ip.get("gateway"):
        parts.append(f"gateway {ip['gateway']}")
    if ip.get("dns_servers"):
        parts.append(f"DNS {ip['dns_servers']}")
    if wifi.get("connected") and wifi.get("ssid"):
        parts.append(f"Wi-Fi '{wifi['ssid']}' signal {wifi.get('signal_pct')}%")
    if conn.get("internet_latency_ms") is not None:
        parts.append(f"internet latency {conn['internet_latency_ms']} ms")
    if not parts:
        return None
    return _fact("network", "Network Configuration", "Network", ", ".join(str(p) for p in parts) + ".",
                 prompt="What is my network configuration (IP, DNS, adapter)?")


def _ports(hw, sw, msg):
    conns = (sw.get("network") or {}).get("connections") or {}
    listening = conns.get("notable_listening") or conns.get("listening_ports") or []
    if not listening:
        return _fact("ports", "Open / Listening Ports", "Network",
                     "No notable listening ports detected.", prompt="Which ports are open?")
    lines = []
    for p in listening[:10]:
        if isinstance(p, dict):
            lines.append(f"port {p.get('port')} ({p.get('process') or p.get('proc') or '?'})")
        else:
            lines.append(str(p))
    return _fact("ports", "Open / Listening Ports", "Network",
                 "Listening: " + ", ".join(lines) + ".", prompt="Which ports are open?")


def _net_devices(hw, sw, msg):
    ext = (hw.get("external_devices") or {})
    neigh = ext.get("network_devices") or {}
    devs = (neigh.get("lan_devices") if isinstance(neigh, dict) else neigh) or []
    if not devs:
        return _fact("net_devices", "Devices on the Network", "Network",
                     "No active LAN neighbours were reachable at scan time. Full device "
                     "discovery (servers, printers, cameras, switches) needs an active "
                     "network sweep, which this single-machine scan does not perform.",
                     prompt="What devices are on my network?")
    lines = []
    for d in devs[:15]:
        tag = "gateway/router" if d.get("is_gateway") else (d.get("manufacturer") or "device")
        lines.append(f"{d.get('ip_address')} [{d.get('mac_address')}] ({tag})")
    return _fact("net_devices", "Devices on the Network", "Network",
                 f"{len(devs)} device(s) seen on the local network: " + "; ".join(lines) + ".",
                 prompt="What devices are on my network?")


def _antivirus(hw, sw, msg):
    sec = sw.get("security") or {}
    defn = sec.get("windows_defender") or {}
    av = sec.get("antivirus_products") or []
    active = sec.get("protection_active")
    parts = [f"Active real-time protection: {_yn(active)}"]
    if av:
        parts.append("AV products: " + ", ".join(a.get("name") for a in av if a.get("name")))
    if defn:
        parts.append(f"Defender real-time: {_yn(defn.get('realtime_protection'))}")
        if defn.get("signature_age_days") is not None:
            parts.append(f"signatures {defn.get('signature_age_days')}d old")
    sev = Severity.info if active else Severity.warning
    steps = ["Protection is active - no action needed."] if active else [
        "Turn on Microsoft Defender real-time protection in Windows Security."]
    return _fact("antivirus", "Antivirus Status", "Security", "; ".join(str(p) for p in parts) + ".",
                 steps=steps, prompt="Is antivirus enabled?", severity=sev)


def _firewall(hw, sw, msg):
    fw = (sw.get("security") or {}).get("firewall") or {}
    if not fw:
        return None
    allon = fw.get("all_enabled")
    sev = Severity.info if allon else Severity.warning
    detail = f"Firewall all profiles enabled: {_yn(allon)}."
    profs = fw.get("profiles")
    if isinstance(profs, list) and profs:
        detail += " Profiles: " + ", ".join(
            f"{p.get('name')}={'on' if p.get('enabled') else 'off'}" for p in profs if isinstance(p, dict))
    steps = ["Firewall is fully enabled - no action needed."] if allon else [
        "Re-enable all firewall profiles in Windows Security > Firewall & network protection."]
    return _fact("firewall", "Firewall Status", "Security", detail, steps=steps,
                 prompt="Is the firewall enabled?", severity=sev)


def _bitlocker(hw, sw, msg):
    bl = (sw.get("security") or {}).get("bitlocker") or {}
    prot = bl.get("system_drive_protected")
    sev = Severity.info if prot else Severity.warning
    steps = ["System drive is encrypted - no action needed."] if prot else [
        "Enable BitLocker on the system drive (Settings > Privacy & security > Device encryption)."]
    return _fact("bitlocker", "Disk Encryption (BitLocker)", "Security",
                 f"System drive encrypted with BitLocker: {_yn(prot)}.", steps=steps,
                 prompt="Is BitLocker enabled?", severity=sev)


def _admins(hw, sw, msg):
    acc = (sw.get("security") or {}).get("local_accounts") or {}
    admins = acc.get("administrators") or []
    if not admins and acc.get("administrator_count") is None:
        return None
    names = ", ".join(str(a) for a in admins[:10]) if admins else "n/a"
    detail = f"Administrator accounts ({acc.get('administrator_count', len(admins))}): {names}."
    if acc.get("guest_account_enabled"):
        detail += " Guest account is ENABLED."
    nopwd = acc.get("accounts_without_password") or []
    if nopwd:
        detail += f" {len(nopwd)} account(s) without a password."
    return _fact("admins", "User & Administrator Accounts", "Security", detail,
                 prompt="Who has administrator access?")


def _security_posture(hw, sw, msg):
    comp = sw.get("compliance") or {}
    sec = sw.get("security") or {}
    susp = ((sw.get("running_processes") or {}).get("suspicious") or [])
    parts = []
    if comp.get("score") is not None:
        parts.append(f"Security/compliance score {comp['score']}/100 ({comp.get('status')})")
    failed = [c for c in (comp.get("controls") or []) if c.get("status") == "fail"]
    if failed:
        parts.append("gaps: " + ", ".join(c.get("name") for c in failed[:5]))
    parts.append(f"active protection: {_yn(sec.get('protection_active'))}")
    if susp:
        parts.append(f"{len(susp)} suspicious process(es) flagged")
    sev = Severity.warning if (failed or susp or sec.get("protection_active") is False) else Severity.info
    steps = [f"Fix: {c.get('detail')}" for c in failed[:5]] or ["No major security gaps detected."]
    return _fact("security_posture", "Security Posture & Risks", "Security",
                 "; ".join(str(p) for p in parts) + ".", steps=steps,
                 prompt="What are my security risks and how secure is this machine?", severity=sev)


def _windows_version(hw, sw, msg):
    os_ = sw.get("operating_system") or {}
    win = os_.get("windows") or {}
    act = os_.get("activation") or {}
    if not win:
        return None
    detail = f"{win.get('edition') or 'Windows'} {win.get('version') or ''} (build {win.get('build_number')})."
    if act.get("activated") is not None:
        detail += f" Activated: {_yn(act.get('activated'))}."
    if win.get("uptime_hours") is not None:
        detail += f" Uptime {round(win['uptime_hours']/24, 1)} days."
    return _fact("windows_version", "Windows Version", "Windows", detail,
                 prompt="What version of Windows am I running?")


def _windows_updates(hw, sw, msg):
    upd = (sw.get("operating_system") or {}).get("updates") or {}
    if not upd:
        return None
    pending = upd.get("pending_count")
    detail = f"{upd.get('installed_count', '?')} updates installed; {pending if pending is not None else '?'} pending."
    recent = upd.get("recent_installed") or []
    if recent:
        names = ", ".join((r.get("hotfix_id") or r.get("id") or str(r)) for r in recent[:5]) if isinstance(recent[0], dict) else ", ".join(str(r) for r in recent[:5])
        detail += f" Recent: {names}."
    sev = Severity.warning if isinstance(pending, (int, float)) and pending >= 1 else Severity.info
    steps = ["Install pending updates via Settings > Windows Update."] if sev == Severity.warning else ["Up to date - no action needed."]
    return _fact("windows_updates", "Windows Updates", "Windows", detail, steps=steps,
                 prompt="Are Windows updates pending?", severity=sev)


def _installed_software(hw, sw, msg):
    apps = sw.get("installed_applications") or []
    count = sw.get("installed_count") or len(apps)
    store = sw.get("store_application_count")
    if not count:
        return None
    detail = f"{count} desktop application(s) installed"
    if store:
        detail += f" plus {store} Microsoft Store app(s)"
    detail += "."
    recent = sw.get("recently_installed_30d") or []
    if recent:
        names = ", ".join((a.get("name") if isinstance(a, dict) else str(a)) for a in recent[:6])
        detail += f" Installed in last 30 days: {names}."
    return _fact("installed_software", "Installed Software", "Software", detail,
                 prompt="What software is installed?")


def _largest_software(hw, sw, msg):
    deep = sw.get("storage_deep") or {}
    foot = deep.get("application_footprint") or {}
    apps = foot.get("applications") or foot.get("top") or []
    if not apps:
        si = sw.get("storage_intelligence") or {}
        apps = (si.get("application_footprint") or {}).get("applications") or []
    if not apps:
        return None
    lines = []
    for a in apps[:8]:
        if isinstance(a, dict):
            lines.append(f"{a.get('name')} ({a.get('estimated_size_gb') or a.get('size_gb')} GB)")
    if not lines:
        return None
    return _fact("largest_software", "Largest Installed Applications", "Storage",
                 "By disk usage: " + "; ".join(lines) + ".",
                 prompt="What software consumes the most storage?")


def _startup_apps(hw, sw, msg):
    st = sw.get("startup_programs") or {}
    progs = st.get("programs") or []
    if not progs:
        return None
    names = ", ".join((p.get("name") if isinstance(p, dict) else str(p)) for p in progs[:12])
    detail = f"{len(progs)} startup item(s): {names}."
    high = st.get("high_impact_count")
    if high:
        detail += f" {high} flagged high-impact."
    return _fact("startup_apps", "Startup Applications", "Software", detail,
                 prompt="What applications start automatically?")


def _least_used(hw, sw, msg):
    ua = sw.get("user_activity") or {}
    least = ua.get("least_used_apps") or []
    most = ua.get("most_used_apps") or []
    if not (least or most):
        return None
    detail = ""
    if least:
        detail += "Rarely used: " + ", ".join(f"{a.get('app')} ({a.get('run_count')}x)" for a in least[:8]) + ". "
    if most:
        detail += "Most used: " + ", ".join(f"{a.get('app')} ({a.get('run_count')}x)" for a in most[:5]) + "."
    return _fact("least_used", "Application Usage", "Software", detail.strip(),
                 steps=["Consider uninstalling rarely used apps to reclaim space and reduce attack surface."],
                 prompt="Which applications are rarely used / should I uninstall?")


def _predictive(hw, sw, msg):
    pred = sw.get("predictive") or {}
    preds = pred.get("predictions") or {}
    if not preds:
        return None
    label = {"ssd_failure": "SSD failure", "battery_failure": "Battery failure",
             "crash_probability": "Crash probability", "resource_exhaustion": "Resource exhaustion",
             "disk_full": "Disk full"}
    lines = []
    for k, v in preds.items():
        if v.get("risk") in (None, "n/a", "low"):
            continue
        lines.append(f"{label.get(k, k)}: {v.get('risk').upper()} - {v.get('detail')}")
    if not lines:
        lines = [f"{label.get(k, k)}: {v.get('risk')}" for k, v in preds.items()]
    sev = Severity.warning if pred.get("high_risk_areas") else Severity.info
    return _fact("predictive", "Predictive Risk", "Predictive", " | ".join(lines),
                 prompt="What should I prepare for / what is likely to fail?", severity=sev)


def _printer_section(hw: dict) -> dict:
    return ((hw.get("external_devices") or {}).get("printers")) or {}


def _printer_connected(hw, sw, msg):
    section = _printer_section(hw)
    printers = section.get("printers") or []
    physical = [p for p in printers if p.get("is_physical")]
    virtual = [p for p in printers if p.get("is_virtual")]
    pnp_usb = section.get("pnp_usb_printers") or []

    if physical:
        lines = []
        for p in physical[:8]:
            conn = p.get("connection") or "Unknown"
            health = p.get("health") or "Unknown"
            default = " (default)" if p.get("is_default") else ""
            lines.append(f"{p.get('name')}{default} - {conn}, {health}")
        detail = (
            f"Yes - {len(physical)} physical printer(s) on this PC: "
            + "; ".join(lines) + "."
        )
        if virtual:
            vnames = ", ".join(p.get("name", "virtual") for p in virtual[:3])
            detail += (
                f" Windows also lists {len(virtual)} software printer(s) "
                f"({vnames}) - these are not physical hardware."
            )
    elif pnp_usb:
        names = ", ".join(p.get("name", "USB printer") for p in pnp_usb[:3])
        detail = (
            f"Partially - USB printer hardware is plugged in ({names}) but Windows "
            "does not have a printer queue set up yet."
        )
    elif virtual:
        vnames = ", ".join(p.get("name", "virtual") for p in virtual[:4])
        detail = (
            f"No - no physical printer is connected. Windows only shows software "
            f"printers: {vnames}."
        )
    else:
        detail = "No - this PC has no printer installed or physically connected."

    steps: list[str] = []
    if not physical:
        steps = [
            "Settings > Bluetooth & devices > Printers & scanners > Add device.",
            "Turn the printer on and connect it (USB or same Wi-Fi/network).",
            "For a network printer, add it by IP if Windows does not auto-detect it.",
        ]
    return _fact(
        "printer_connected",
        "Printer Connection",
        "Printers",
        detail,
        steps=steps,
        prompt="Is my laptop connected to any printer?",
    )


def _printers(hw, sw, msg):
    section = _printer_section(hw)
    printers = section.get("printers") or []
    virtual = [p for p in printers if p.get("is_virtual")]
    network_installed = section.get("network_installed") or [
        p for p in printers if p.get("is_physical") and p.get("connection") == "Network"
    ]
    discovered = section.get("network_discovered") or []
    network_available = section.get("network_available") or (network_installed + [
        {"name": d.get("name"), "network_address": d.get("ip_address"),
         "health": "Reachable", "is_discovered": True}
        for d in discovered
    ])

    names: list[str] = []
    for p in network_available[:12]:
        label = (p.get("name") or "Network printer").strip()
        addr = p.get("network_address") or p.get("ip_address")
        if addr and addr not in label:
            label += f" ({addr})"
        status = p.get("health") or p.get("status")
        if p.get("is_discovered"):
            label += " [discovered, not installed on this PC]"
        elif status and str(status).lower() not in ("ready", "normal", "idle / ready"):
            label += f" [{status}]"
        names.append(label)

    count = len(network_available)
    if names:
        detail = (
            f"{count} network printer(s) on your LAN: "
            + "; ".join(names)
            + "."
        )
    else:
        detail = (
            "No network printers were found on your LAN. "
            "The scan checked installed printer queues and probed reachable devices "
            "for printer ports (RAW/IPP/LPD). "
            "Printers that are powered off or on a different subnet will not appear."
        )

    local = section.get("local_installed_count") or sum(
        1 for p in printers if p.get("is_physical") and p.get("connection") == "Local / USB"
    )
    if local:
        local_names = [
            p.get("name") or "Local printer"
            for p in printers
            if p.get("is_physical") and p.get("connection") == "Local / USB"
        ][:6]
        detail += f" Also {local} USB/local printer(s) on this PC: {', '.join(local_names)}."

    if virtual and not is_printer_connection_question(msg):
        vnames = ", ".join(p.get("name", "virtual") for p in virtual[:4])
        detail += (
            f" Windows also lists {len(virtual)} software printer(s) "
            f"({vnames}) - these are not physical network hardware."
        )

    steps: list[str] = []
    if discovered and not network_installed:
        steps = [
            "Settings > Bluetooth & devices > Printers & scanners > Add device.",
            "If auto-detect misses a printer, add it manually by IP address.",
        ]
    elif not names:
        steps = [
            "Confirm the printer is powered on and connected to the same Wi-Fi/LAN.",
            "Settings > Bluetooth & devices > Printers & scanners > Add device.",
            "For a network printer, add it by IP if Windows does not auto-detect it.",
        ]
    return _fact(
        "printers_network",
        "Printers on Your Network",
        "Printers",
        detail,
        steps=steps,
        prompt="How many printers are available on my network?",
    )


# (regex, builder) - first match per builder wins; multiple builders can fire.
_TOPICS: list[tuple[re.Pattern[str], Callable]] = [
    (re.compile(
        r"\b(?:"
        r"which\s+(?:app|application|process|program).{0,50}?(?:cpu|processor)|"
        r"which\s+(?:app|application|process|program).{0,50}?(?:most|more).{0,20}?(?:cpu|processor)|"
        r"what\s+(?:app|application|process|program).{0,50}?(?:cpu|processor|most\s+cpu|more\s+cpu)|"
        r"(?:app|application|process|program).{0,40}?(?:using|uses|consumes).{0,25}?(?:most|more).{0,20}?(?:cpu|processor)|"
        r"(?:most|highest|top).{0,25}?(?:cpu|processor).{0,40}(?:app|application|process|program)"
        r")\b",
        re.I,
    ), _top_cpu_application),
    (re.compile(
        r"\b(?:"
        r"which\s+(?:app|application|process|program).{0,50}?(?:ram|memory)|"
        r"which\s+(?:app|application|process|program).{0,50}?(?:most|more).{0,20}?(?:ram|memory)|"
        r"what\s+(?:app|application|process|program).{0,50}?(?:ram|memory|most\s+ram|more\s+ram)|"
        r"(?:app|application|process|program).{0,40}?(?:using|uses|consumes).{0,25}?(?:most|more).{0,20}?(?:ram|memory)|"
        r"(?:most|highest|top).{0,25}?(?:ram|memory).{0,40}(?:app|application|process|program)"
        r")\b",
        re.I,
    ), _top_ram_application),
    (re.compile(
        r"\b(?:"
        r"which\s+file|what\s+file|biggest\s+file|largest\s+file|"
        r"(?:which|what)\s+(?:file|folder).{0,40}(?:most|more)\s+space|"
        r"taking\s+(?:the\s+)?(?:most|more)\s+space|"
        r"what(?:'s| is)\s+using\s+(?:the\s+)?(?:most|more)\s+space"
        r")\b",
        re.I,
    ), _largest_file),
    (re.compile(r"\b(cpu|processor)\b", re.I), _cpu),
    (re.compile(r"\b(gpu|graphics|video\s+card)", re.I), _gpu),
    (re.compile(r"\b(ram|memory)\b", re.I), _ram),
    (re.compile(r"\b(motherboard|mainboard|chipset)", re.I), _motherboard),
    (re.compile(r"\b(bios|uefi)\b", re.I), _motherboard),
    (re.compile(r"\b(serial\s+number|service\s+tag|asset\s+tag|what\s+(model|machine))", re.I), _serial),
    (re.compile(r"\b(storage\s+device|drives?\s+(connected|installed)|what\s+(drives|disks)|disks?\s+connected)", re.I), _storage),
    (re.compile(r"\b(ssd|nvme|hdd|disk\s+health|smart|healthy.*(ssd|disk|drive)|how\s+healthy)", re.I), _ssd_health),
    (re.compile(r"\b(battery|charge\s+cycle|charger|wear)", re.I), _battery),
    (re.compile(r"\b(virtuali[sz]ation|vt-?x|amd-?v)", re.I), _virtualization),
    (re.compile(r"\b(overheat|thermal|throttl|temperature|hot)", re.I), _thermal),
    (re.compile(r"\busb\b", re.I), _usb),
    (re.compile(r"\b(monitor|display|hdr|screen)", re.I), _monitors),
    (re.compile(
        r"\b(?:"
        r"(?:audio|sound|microphone|mic|speaker|headphone|headset).{0,50}?(?:devices?|connected|attached|plugged)|"
        r"(?:tell\s+me|list|show|what|which).{0,40}?(?:audio|sound|microphone|mic|speaker).{0,30}?devices?|"
        r"devices?\s+connected.{0,30}?(?:audio|sound|microphone|mic|speaker)|"
        r"audio\s+devices?\s+connected|"
        r"(?:audio|sound|microphone|mic|speaker|headphone|headset)\s+devices?\b"
        r")\b",
        re.I,
    ), _audio_devices),
    (re.compile(
        r"\b(?:bluetooth|bt).{0,40}?(?:devices?|connected|paired)|"
        r"devices?\s+connected.{0,30}?bluetooth\b",
        re.I,
    ), _bluetooth_devices),
    (re.compile(
        r"\b(?:webcam|web\s*cam|camera).{0,40}?(?:devices?|connected|attached)|"
        r"devices?\s+connected.{0,30}?(?:camera|webcam)\b",
        re.I,
    ), _webcam_devices),
    (re.compile(
        r"\b(?:list|show|enumerate)\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?drivers?\b|"
        r"\b(?:list|show)\s+(?:me\s+)?(?:all\s+)?(?:installed\s+)?drivers?\b|"
        r"\bdriver\s+inventory\b",
        re.I,
    ), _list_drivers),
    (re.compile(
        r"\b(?:driver|drivers).{0,40}?(?:fail(?:ing|ed)|broken|error|problem)|"
        r"(?:fail(?:ing|ed)|broken|error|problem).{0,40}?(?:driver|drivers)|"
        r"\bwhich\s+drivers?\s+(?:are\s+)?(?:fail|broken|error|problem)|"
        r"\bwhat\s+drivers?\s+(?:are\s+)?(?:fail|broken|error|problem)",
        re.I,
    ), _failing_drivers),
    (re.compile(r"\b(machine\s+health|overall\s+health|health\s+score)\b", re.I), _health_score),
    (re.compile(r"\b(wifi|wi-?fi|wireless|wlan|ssid|hotspot)\b", re.I), _wifi),
    (re.compile(r"\b(ip\s+address|dns|network\s+adapter|adapter\s+active|active\s+adapter|wifi\s+signal|signal\s+strength)", re.I), _network_status),
    (re.compile(r"\b(open\s+port|listening|which\s+port|ports?\s+are\s+open)", re.I), _ports),
    (re.compile(r"(on\s+(?:my|the)\s+network|network\s+device|\bnas\b|servers?\s+(?:are\s+)?(?:available|online)|devices?\s+(?:are\s+)?(?:online|active)|hosts?\s+(?:are\s+)?(?:online|unreachable|active))", re.I), _net_devices),
    (re.compile(r"\b(antivirus|defender|virus\s+protection)", re.I), _antivirus),
    (re.compile(r"\bfirewall", re.I), _firewall),
    (re.compile(r"\b(bitlocker|encrypt)", re.I), _bitlocker),
    (re.compile(r"\b(administrator|admin\s+(access|account)|elevated\s+privile|user\s+account)", re.I), _admins),
    (re.compile(r"\b(security\s+risk|how\s+secure|vulnerab|suspicious|malware|secure\s+is\s+this|unsigned|installed\s+silently|silently)", re.I), _security_posture),
    (re.compile(r"\b(version\s+of\s+windows|which\s+windows|windows.*running|windows\s+edition)", re.I), _windows_version),
    (re.compile(r"\b(updates?\s+(pending|installed|available)|are\s+updates|pending\s+updates|windows\s+update)", re.I), _windows_updates),
    (re.compile(r"\b(software\s+(is\s+)?installed|what\s+software|installed\s+(software|applications)|list.*(software|apps)|applications.*installed)", re.I), _installed_software),
    (re.compile(r"\b(largest\s+(installed\s+)?(app|application|software)|software.*storage|consumes?\s+the\s+most\s+storage|disk\s+space.*app)", re.I), _largest_software),
    (re.compile(r"\b(start\s+automatically|startup\s+(app|program|item))", re.I), _startup_apps),
    (re.compile(r"\b(rarely\s+used|not\s+been\s+used|uninstall|least\s+used|not\s+used\s+recently)", re.I), _least_used),
    (re.compile(r"\b(predict|failure\s+risk|likely\s+to\s+fail|prepare\s+for|operational\s+risk)", re.I), _predictive),
    (re.compile(
        r"\b(?:connected\s+to\s+(?:any\s+)?printers?|"
        r"(?:is|are)\s+(?:my\s+)?(?:laptop|pc|computer|machine)?\s*(?:connected\s+to\s+)?(?:any\s+)?printers?|"
        r"any\s+printers?\s+connected|printers?\s+connected)\b",
        re.I,
    ), _printer_connected),
    (re.compile(r"\b(how\s+many\s+printer|printers?\s+(?:are\s+)?(?:available|on|in|connected)|"
                r"list\s+printer|what\s+printer|which\s+printer|show\s+printer|"
                r"printer.*(?:network|lan)|(?:network|lan).*printer|"
                r"available\s+(?:on|in)\s+(?:my\s+)?network)", re.I), _printers),
]


_DOMAIN_STATUS_BUILDERS: dict[str, Callable] = {
    "audio": _audio_devices,
    "bluetooth": _bluetooth_devices,
    "webcam": _webcam_devices,
    "wifi": _wifi,
    "printer": _printer_connected,
    "network": _network_status,
    "display": _monitors,
    "driver": _driver_domain_answer,
}


def build_domain_status_finding(
    domain: str,
    hw: dict,
    sw: dict,
    message: str,
) -> TroubleshooterFinding | None:
    """Domain-level status fallback when topic regex did not match."""
    builder = _DOMAIN_STATUS_BUILDERS.get(domain)
    if not builder:
        return None
    try:
        return builder(hw, sw, message)
    except Exception:
        return None


def _unavailable_finding(profile: IssueProfile) -> TroubleshooterFinding:
    domain = profile.primary_domain or "system"
    label = domain.replace("_", " ")
    return _fact(
        "unavailable",
        f"{label.title()} Status",
        label.title(),
        f"Could not determine {label} status from the scan data for this question.",
        prompt="",
    )


def build_scan_only_findings(
    hw: dict,
    sw: dict,
    message: str,
    profile: IssueProfile,
    report: dict | None = None,
) -> list[TroubleshooterFinding]:
    """Answer informational / inventory questions from scan data only."""
    if not is_scan_only_intent(profile.query_intent):
        return []

    if is_top_ram_question(message):
        top_ram = _top_ram_application(hw, sw, message)
        if top_ram:
            return [top_ram]

    if is_top_cpu_question(message):
        top_cpu = _top_cpu_application(hw, sw, message)
        if top_cpu:
            return [top_cpu]

    if is_largest_file_question(message):
        largest = _largest_file(hw, sw, message, report)
        if largest:
            return [largest]

    findings = build_info_findings(hw, sw, message, profile)
    if not findings:
        domains_to_try: list[str] = []
        if profile.primary_domain:
            domains_to_try.append(profile.primary_domain)
        for d in profile.domains:
            if d not in domains_to_try:
                domains_to_try.append(d)
        for domain in domains_to_try:
            fallback = build_domain_status_finding(domain, hw, sw, message)
            if fallback:
                findings = [fallback]
                break

    if not findings:
        from app.services.scan_data_responder import respond_from_scan
        resp = respond_from_scan(
            hw, sw, message, profile,
            health_report=(report or {}).get("health_report"),
        )
        if resp:
            findings = [resp]

    if not findings:
        findings = [_unavailable_finding(profile)]
    if profile.query_intent == "inventory" and _LIST_INVENTORY_RE.search(message or ""):
        return findings[:1]
    return findings[:8]


def build_info_findings(
    hw: dict,
    sw: dict,
    message: str,
    profile: IssueProfile | None = None,
) -> list[TroubleshooterFinding]:
    """Return Severity.info findings answering factual questions in ``message``."""
    intent = (
        profile.query_intent if profile and profile.query_intent
        else classify_query_intent(message)
    )
    if not is_scan_only_intent(intent):
        return []
    hw = hw or {}
    sw = sw or {}
    out: list[TroubleshooterFinding] = []
    seen_builders: set[Any] = set()
    seen_titles: set[str] = set()
    for pat, builder in _TOPICS:
        if builder in seen_builders:
            continue
        if builder is _printers and is_printer_connection_question(message or ""):
            continue
        if builder is _cpu and is_top_cpu_question(message or ""):
            continue
        if builder is _ram and is_top_ram_question(message or ""):
            continue
        if builder is _storage and is_largest_file_question(message or ""):
            continue
        if not pat.search(message or ""):
            continue
        seen_builders.add(builder)
        try:
            f = builder(hw, sw, message)
        except Exception:
            f = None
        if f and f.title not in seen_titles:
            seen_titles.add(f.title)
            out.append(f)
    return out[:6]
