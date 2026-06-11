"""Security scanner: Defender, firewall, BitLocker, TPM, Secure Boot, UAC,
RDP, SMBv1, local accounts and antivirus products - full security posture."""
from __future__ import annotations

from app.services.scanners.base import (
    IS_WINDOWS,
    as_list,
    cim,
    cim_one,
    ps_json,
    safe_scan,
    to_int,
)

_NEVER = 4294967295  # Defender uses uint32 max for "never ran"


def _defender() -> dict:
    rec = cim_one(
        "MSFT_MpComputerStatus",
        "AMRunningMode,AntivirusEnabled,RealTimeProtectionEnabled,AntispywareEnabled,"
        "AntivirusSignatureVersion,AntivirusSignatureAge,NISEnabled,IoavProtectionEnabled,"
        "BehaviorMonitorEnabled,TamperProtectionSource,IsTamperProtected,"
        "QuickScanAge,FullScanAge,AMEngineVersion,AMProductVersion",
        namespace="root/microsoft/windows/defender",
        timeout=25.0,
    ) or {}

    def _age(value):
        v = to_int(value)
        return None if v is None or v >= _NEVER else v

    return {
        "running_mode": rec.get("AMRunningMode"),
        "antivirus_enabled": rec.get("AntivirusEnabled"),
        "realtime_protection": rec.get("RealTimeProtectionEnabled"),
        "antispyware_enabled": rec.get("AntispywareEnabled"),
        "behavior_monitoring": rec.get("BehaviorMonitorEnabled"),
        "network_protection": rec.get("NISEnabled"),
        "tamper_protection": rec.get("IsTamperProtected"),
        "engine_version": rec.get("AMEngineVersion"),
        "signature_version": rec.get("AntivirusSignatureVersion"),
        "signature_age_days": _age(rec.get("AntivirusSignatureAge")),
        "last_quick_scan_days_ago": _age(rec.get("QuickScanAge")),
        "last_full_scan_days_ago": _age(rec.get("FullScanAge")),
    }


def _firewall() -> dict:
    rows = as_list(ps_json(
        "Get-NetFirewallProfile -ErrorAction SilentlyContinue | "
        "Select-Object Name,@{N='Enabled';E={[bool]$_.Enabled}},"
        "@{N='In';E={$_.DefaultInboundAction.ToString()}},"
        "@{N='Out';E={$_.DefaultOutboundAction.ToString()}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    profiles = {r.get("Name"): r.get("Enabled") for r in rows}
    return {
        "profiles": profiles,
        "default_actions": {
            r.get("Name"): {"inbound": r.get("In"), "outbound": r.get("Out")} for r in rows
        },
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
        "@{N='Encryption';E={$_.VolumeStatus.ToString()}},"
        "@{N='Method';E={$_.EncryptionMethod.ToString()}},EncryptionPercentage | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    volumes = [{
        "mount": r.get("MountPoint"),
        "protection": r.get("Protection"),
        "encryption": r.get("Encryption"),
        "method": r.get("Method"),
        "encrypted_pct": r.get("EncryptionPercentage"),
    } for r in rows]
    system_protected = any(
        (v.get("mount") or "").upper().startswith("C") and v.get("protection") == "On"
        for v in volumes
    )
    return {"volumes": volumes, "system_drive_protected": system_protected}


def _tpm() -> dict:
    """TPM chip state - required for Windows 11 / enterprise attestation."""
    rec = ps_json(
        "try { Get-Tpm -ErrorAction Stop | Select-Object TpmPresent,TpmReady,TpmEnabled,"
        "TpmActivated,ManufacturerIdTxt,ManufacturerVersion | ConvertTo-Json -Compress } "
        "catch { '{}' }",
        timeout=20.0,
    ) or {}
    spec = cim_one("Win32_Tpm", "SpecVersion",
                   namespace="root/cimv2/Security/MicrosoftTpm", timeout=15.0) or {}
    version = (spec.get("SpecVersion") or "").split(",")[0].strip() or None
    has_data = version is not None or any(
        rec.get(k) is not None
        for k in ("TpmPresent", "TpmReady", "TpmEnabled", "TpmActivated")
    )
    if not has_data:
        return {"available": False, "note": "TPM state not readable (may need admin rights)."}
    return {
        "available": True,
        "present": rec.get("TpmPresent"),
        "ready": rec.get("TpmReady"),
        "enabled": rec.get("TpmEnabled"),
        "activated": rec.get("TpmActivated"),
        "manufacturer": rec.get("ManufacturerIdTxt"),
        "spec_version": version,
    }


def _secure_boot() -> dict:
    rec = ps_json(
        "try { @{enabled=[bool](Confirm-SecureBootUEFI -ErrorAction Stop)} | ConvertTo-Json -Compress } "
        "catch [System.PlatformNotSupportedException] { '{\"enabled\":false,\"note\":\"Legacy BIOS (no UEFI)\"}' } "
        "catch { '{\"enabled\":null,\"note\":\"Not readable (needs admin)\"}' }",
        timeout=15.0,
    ) or {}
    return {"enabled": rec.get("enabled"), "note": rec.get("note")}


def _uac() -> dict:
    rec = ps_json(
        "Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System' "
        "-ErrorAction SilentlyContinue | Select-Object EnableLUA,ConsentPromptBehaviorAdmin | "
        "ConvertTo-Json -Compress",
        timeout=15.0,
    ) or {}
    enabled = rec.get("EnableLUA")
    return {"enabled": bool(enabled) if enabled is not None else None}


def _remote_access() -> dict:
    rec = ps_json(
        "$rdp=(Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server' "
        "-ErrorAction SilentlyContinue).fDenyTSConnections;"
        "$smb1=$null; try{$smb1=(Get-SmbServerConfiguration -ErrorAction Stop).EnableSMB1Protocol}catch{};"
        "@{rdp_denied=$rdp; smb1=$smb1} | ConvertTo-Json -Compress",
        timeout=20.0,
    ) or {}
    rdp_denied = rec.get("rdp_denied")
    return {
        "rdp_enabled": (rdp_denied == 0) if rdp_denied is not None else None,
        "smb1_enabled": rec.get("smb1"),
    }


def _local_accounts() -> dict:
    """Local administrators + risky account states (guest enabled, no-password)."""
    admins = as_list(ps_json(
        # SID S-1-5-32-544 = built-in Administrators group (locale independent).
        "Get-LocalGroupMember -SID 'S-1-5-32-544' -ErrorAction SilentlyContinue | "
        "Select-Object Name,@{N='Source';E={$_.PrincipalSource.ToString()}},"
        "@{N='Class';E={$_.ObjectClass}} | ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    users = as_list(ps_json(
        "Get-LocalUser -ErrorAction SilentlyContinue | "
        "Select-Object Name,Enabled,PasswordRequired,@{N='Sid';E={$_.SID.Value}} | "
        "ConvertTo-Json -Compress",
        timeout=20.0,
    ))
    guest_enabled = any(
        (u.get("Sid") or "").endswith("-501") and u.get("Enabled") for u in users
    )
    no_password = [
        u.get("Name") for u in users
        if u.get("Enabled") and u.get("PasswordRequired") is False
    ]
    return {
        "administrators": [
            {"name": a.get("Name"), "source": a.get("Source"), "type": a.get("Class")}
            for a in admins
        ],
        "administrator_count": len(admins),
        "local_users_enabled": sum(1 for u in users if u.get("Enabled")),
        "guest_account_enabled": guest_enabled,
        "accounts_without_password": no_password,
    }


@safe_scan("security")
def scan() -> dict:
    if not IS_WINDOWS:
        return {"available": False, "note": "Security diagnostics require Windows."}

    from concurrent.futures import ThreadPoolExecutor

    jobs = {
        "windows_defender": _defender,
        "firewall": _firewall,
        "antivirus_products": _antivirus_products,
        "bitlocker": _bitlocker,
        "tpm": _tpm,
        "secure_boot": _secure_boot,
        "uac": _uac,
        "remote_access": _remote_access,
        "local_accounts": _local_accounts,
    }
    out: dict = {"available": True}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs.items()}
        for fut, key in futures.items():
            try:
                out[key] = fut.result(timeout=45)
            except Exception as exc:  # pragma: no cover
                out[key] = {"error": str(exc)}

    defender = out.get("windows_defender") or {}
    av = out.get("antivirus_products") or []
    third_party = [a for a in av if isinstance(a, dict) and a.get("name")
                   and "defender" not in (a["name"] or "").lower()]
    protection_active = (
        defender.get("realtime_protection") is True
        or any(a.get("enabled") for a in third_party)
    )
    out["protection_active"] = protection_active
    out["disabled_protection"] = not protection_active
    return out
