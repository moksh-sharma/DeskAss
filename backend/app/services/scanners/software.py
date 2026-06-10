"""Installed-software scanner: full app list + category detection."""
from __future__ import annotations

from app.services.scanners.base import safe_scan

# Category -> keywords matched against installed-app display names (lowercased).
_CATEGORIES: dict[str, list[str]] = {
    "Microsoft": ["microsoft office", "outlook", "microsoft teams", "onedrive", "microsoft edge", "microsoft 365"],
    "Browsers": ["chrome", "firefox", "brave", "opera", "edge", "vivaldi"],
    "Development": ["visual studio code", "cursor", "python", "java", "node", "docker", "git", "intellij", "pycharm"],
    "Security": ["defender", "crowdstrike", "sentinelone", "mcafee", "sophos", "norton", "kaspersky", "bitdefender"],
    "VPN": ["anyconnect", "forticlient", "globalprotect", "openvpn", "zscaler", "nordvpn", "expressvpn"],
    "Database": ["sql server", "postgresql", "mysql", "mongodb", "redis", "sqlite"],
    "Virtualization": ["vmware", "virtualbox", "hyper-v", "vagrant", "wsl"],
}


def _categorize(apps: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {cat: [] for cat in _CATEGORIES}
    for app in apps:
        name_l = (app.get("name") or "").lower()
        for cat, keywords in _CATEGORIES.items():
            if any(k in name_l for k in keywords):
                out[cat].append(app)
    return out


@safe_scan("installed_software")
def scan(inventory=None) -> dict:
    apps: list[dict] = []
    if inventory is not None:
        for ia in getattr(inventory, "installed_apps", []) or []:
            apps.append({
                "name": getattr(ia, "name", None),
                "version": getattr(ia, "version", None),
                "publisher": getattr(ia, "publisher", None),
                "install_date": getattr(ia, "install_date", None),
            })
    apps.sort(key=lambda a: (a.get("name") or "").lower())
    return {
        "total_count": len(apps),
        "applications": apps,
        "by_category": _categorize(apps),
    }
