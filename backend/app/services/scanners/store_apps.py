"""Microsoft Store (Appx/UWP) application scanner.

Complements the Win32 installed-software inventory with packaged Store apps,
which do not appear in the standard uninstall registry.
"""
from __future__ import annotations

from app.services.scanners.base import as_list, ps_json, safe_scan

_MAX = 300


@safe_scan("store_apps")
def scan() -> dict:
    rows = as_list(ps_json(
        "Get-AppxPackage -ErrorAction SilentlyContinue | "
        "Where-Object { -not $_.IsFramework } | "
        "Select-Object Name,Version,Publisher,"
        "@{N='SignatureKind';E={$_.SignatureKind.ToString()}},"
        "InstallLocation | ConvertTo-Json -Compress",
        timeout=30.0,
    ))
    apps = []
    for r in rows:
        name = r.get("Name")
        if not name:
            continue
        apps.append({
            "name": name,
            "version": r.get("Version"),
            "publisher": r.get("Publisher"),
            "signature_kind": r.get("SignatureKind"),
            "install_location": r.get("InstallLocation"),
        })
    apps.sort(key=lambda a: (a.get("name") or "").lower())
    store_signed = sum(1 for a in apps if a.get("signature_kind") == "Store")
    return {
        "total_count": len(apps),
        "store_signed_count": store_signed,
        "applications": apps[:_MAX],
        "truncated": len(apps) > _MAX,
        "available": True,
    }
