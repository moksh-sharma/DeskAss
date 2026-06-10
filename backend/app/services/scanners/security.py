"""Security scanner: Defender, firewall, BitLocker, antivirus products."""
from __future__ import annotations

from app.services.scanners.base import IS_WINDOWS, as_list, cim, cim_one, ps_json, safe_scan


def _defender() -> dict:
    rec = cim_one(
        "MSFT_MpComputerStatus",
        "AMRunningMode,AntivirusEnabled,RealTimeProtectionEnabled,AntispywareEnabled,"
        "AntivirusSignatureLastUpdated,NISEnabled,IoavProtectionEnabled",
        namespace="root/microsoft/windows/defender",
        timeout=25.0,
    ) or {}
    return {
        "running_mode": rec.get("AMRunningMode"),
        "antivirus_enabled": rec.get("AntivirusEnabled"),
        "realtime_protection": rec.get("RealTimeProtectionEnabled"),
        "antispyware_enabled": rec.get("AntispywareEnabled"),
        "network_protection": rec.get("NISEnabled"),
    }


def _firewall() -> dict:
    rows = as_list(ps_json(
        "Get-NetFirewallProfile -ErrorAction SilentlyContinue | "
        "Select-Object Name,@{N='Enabled';E={[bool]$_.Enabled}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    profiles = {r.get("Name"): r.get("Enabled") for r in rows}
    return {
        "profiles": profiles,
        "all_enabled": bool(profiles) and all(profiles.values()),
    }


def _antivirus_products() -> list[dict]:
    # SecurityCenter2 lists registered AV products (real value: third-party AVs).
    rows = cim("AntiVirusProduct", "displayName,productState",
               namespace="root/SecurityCenter2", timeout=20.0)
    out = []
    for r in rows:
        state = r.get("productState")
        # Decode productState bitmask: 0x1000 in 2nd byte => enabled.
        enabled = None
        try:
            hex_state = f"{int(state):06x}"
            enabled = hex_state[2:4] in ("10", "11")
        except (TypeError, ValueError):
            pass
        out.append({"name": r.get("displayName"), "enabled": enabled})
    return out


def _bitlocker() -> dict:
    rows = as_list(ps_json(
        "Get-BitLockerVolume -ErrorAction SilentlyContinue | "
        "Select-Object MountPoint,@{N='Protection';E={$_.ProtectionStatus.ToString()}},"
        "@{N='Encryption';E={$_.VolumeStatus.ToString()}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    volumes = [{
        "mount": r.get("MountPoint"),
        "protection": r.get("Protection"),
        "encryption": r.get("Encryption"),
    } for r in rows]
    system_protected = any(
        (v.get("mount") or "").upper().startswith("C") and v.get("protection") == "On"
        for v in volumes
    )
    return {"volumes": volumes, "system_drive_protected": system_protected}


@safe_scan("security")
def scan() -> dict:
    if not IS_WINDOWS:
        return {"available": False, "note": "Security diagnostics require Windows."}
    defender = _defender()
    firewall = _firewall()
    av = _antivirus_products()
    bitlocker = _bitlocker()

    third_party = [a for a in av if a.get("name") and "defender" not in (a["name"] or "").lower()]
    protection_active = (
        defender.get("realtime_protection") is True
        or any(a.get("enabled") for a in third_party)
    )
    return {
        "available": True,
        "windows_defender": defender,
        "firewall": firewall,
        "antivirus_products": av,
        "bitlocker": bitlocker,
        "protection_active": protection_active,
        "disabled_protection": not protection_active,
    }
