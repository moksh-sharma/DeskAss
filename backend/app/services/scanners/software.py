"""Installed-software scanner: full app list, categories, publishers, recency."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services.scanners.base import safe_scan

# Category -> keywords matched against installed-app display names (lowercased).
_CATEGORIES: dict[str, list[str]] = {
    "Microsoft": ["microsoft office", "outlook", "microsoft teams", "onedrive", "microsoft edge", "microsoft 365"],
    "Browsers": ["chrome", "firefox", "brave", "opera", "edge", "vivaldi"],
    "Development": ["visual studio code", "cursor", "python", "java", "node", "docker", "git", "intellij", "pycharm",
                    "android studio", "postman", "kubernetes", ".net sdk", "rust", "golang", "anaconda"],
    "Security": ["defender", "crowdstrike", "sentinelone", "mcafee", "sophos", "norton", "kaspersky", "bitdefender",
                 "malwarebytes", "eset", "trend micro", "carbon black", "cylance"],
    "VPN": ["anyconnect", "forticlient", "globalprotect", "openvpn", "zscaler", "nordvpn", "expressvpn", "wireguard",
            "tailscale", "pulse secure"],
    "Database": ["sql server", "postgresql", "mysql", "mongodb", "redis", "sqlite", "oracle database", "dbeaver"],
    "Virtualization": ["vmware", "virtualbox", "hyper-v", "vagrant", "wsl"],
    "Communication": ["slack", "zoom", "discord", "webex", "skype", "telegram", "whatsapp", "signal"],
    "Remote access": ["teamviewer", "anydesk", "remote desktop", "vnc", "logmein", "splashtop", "rustdesk",
                      "chrome remote"],
    "Media": ["vlc", "spotify", "itunes", "obs", "audacity", "adobe premiere", "photoshop", "gimp"],
    "Cloud storage": ["dropbox", "google drive", "box", "icloud", "mega", "sync.com"],
    "Runtimes": ["visual c++", "redistributable", ".net runtime", ".net framework", "java 8", "jre", "jdk",
                 "directx", "webview2"],
    "Drivers & firmware": ["driver", "chipset", "firmware", "nvidia", "amd software", "intel graphics", "realtek"],
    "Gaming": ["steam", "epic games", "battle.net", "riot", "xbox", "ea app", "ubisoft"],
}

# Remote-admin tools worth surfacing explicitly in an enterprise audit.
_REMOTE_TOOL_HINTS = ("teamviewer", "anydesk", "rustdesk", "logmein", "splashtop", "ammyy", "vnc")


def _categorize(apps: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {cat: [] for cat in _CATEGORIES}
    for app in apps:
        name_l = (app.get("name") or "").lower()
        for cat, keywords in _CATEGORIES.items():
            if any(k in name_l for k in keywords):
                out[cat].append(app)
    return out


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def _recently_installed(apps: list[dict], days: int = 30) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for app in apps:
        dt = _parse_date(app.get("install_date"))
        if dt and dt >= cutoff:
            recent.append({**app, "_installed": dt})
    recent.sort(key=lambda a: a["_installed"], reverse=True)
    return [{k: v for k, v in a.items() if k != "_installed"} for a in recent]


def _publisher_stats(apps: list[dict]) -> dict:
    counts: dict[str, int] = {}
    unknown = 0
    for app in apps:
        pub = (app.get("publisher") or "").strip()
        if not pub:
            unknown += 1
            continue
        counts[pub] = counts.get(pub, 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:15]
    return {
        "distinct_publishers": len(counts),
        "top_publishers": [{"publisher": p, "app_count": c} for p, c in top],
        "unknown_publisher_count": unknown,
    }


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
    by_category = _categorize(apps)
    remote_tools = [
        a for a in apps
        if any(h in (a.get("name") or "").lower() for h in _REMOTE_TOOL_HINTS)
    ]
    return {
        "total_count": len(apps),
        "applications": apps,
        "by_category": by_category,
        "category_counts": {cat: len(items) for cat, items in by_category.items() if items},
        "recently_installed_30d": _recently_installed(apps),
        "publishers": _publisher_stats(apps),
        "remote_access_tools": remote_tools,
    }
