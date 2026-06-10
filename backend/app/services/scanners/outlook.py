"""Outlook scanner: version, profiles, OST/PST sizes, add-ins."""
from __future__ import annotations

import os

from app.services.scanners.base import IS_WINDOWS, as_list, ps_json, safe_scan

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")


def _data_files() -> list[dict]:
    files = []
    roots = [
        os.path.join(LOCALAPPDATA, "Microsoft", "Outlook"),
        os.path.join(os.environ.get("USERPROFILE", ""), "Documents", "Outlook Files"),
    ]
    for root in roots:
        try:
            if not os.path.isdir(root):
                continue
            for entry in os.scandir(root):
                if entry.name.lower().endswith((".ost", ".pst")):
                    size_gb = round(entry.stat().st_size / (1024 ** 3), 2)
                    files.append({
                        "file": entry.name,
                        "type": entry.name.split(".")[-1].upper(),
                        "size_gb": size_gb,
                        "oversized": size_gb >= 45,  # near classic 50 GB limit
                    })
        except Exception:
            continue
    return files


def _addins() -> list[dict]:
    if not IS_WINDOWS:
        return []
    rows = as_list(ps_json(
        "$paths=@('HKCU:\\Software\\Microsoft\\Office\\Outlook\\Addins',"
        "'HKLM:\\Software\\Microsoft\\Office\\Outlook\\Addins',"
        "'HKLM:\\Software\\WOW6432Node\\Microsoft\\Office\\Outlook\\Addins');"
        "$out=@();foreach($p in $paths){if(Test-Path $p){Get-ChildItem $p | ForEach-Object{"
        "$lc=(Get-ItemProperty $_.PSPath).LoadBehavior;"
        "$out+=[pscustomobject]@{Name=$_.PSChildName;LoadBehavior=$lc}}}};"
        "$out | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    out = []
    for r in rows:
        lb = r.get("LoadBehavior")
        out.append({
            "name": r.get("Name"),
            "status": "Active" if lb in (3, 9) else ("Disabled" if lb in (0, 2) else "Inactive"),
            "load_behavior": lb,
        })
    return out


def _version(inventory) -> str | None:
    if inventory is None:
        return None
    for ia in getattr(inventory, "installed_apps", []) or []:
        n = (getattr(ia, "name", "") or "").lower()
        if "outlook" in n or "microsoft 365" in n or "office" in n:
            v = getattr(ia, "version", None)
            if v:
                return v
    return None


@safe_scan("outlook_diagnostics")
def scan(inventory=None) -> dict:
    installed = False
    if inventory is not None:
        installed = any("outlook" in (getattr(ia, "name", "") or "").lower()
                        for ia in getattr(inventory, "installed_apps", []) or [])
    data_files = _data_files()
    addins = _addins()
    return {
        "installed": installed or bool(data_files),
        "version": _version(inventory),
        "data_files": data_files,
        "oversized_files": [f for f in data_files if f.get("oversized")],
        "addins": addins,
        "addin_count": len(addins),
        "disabled_addins": [a for a in addins if a.get("status") == "Disabled"],
    }
