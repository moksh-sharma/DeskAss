"""Compliance evaluator: turns the raw security/OS signals already collected by
the scan into pass/fail control verdicts and an overall compliance score.

This is a synthesis layer - it reads sections produced by other scanners and a
couple of cheap live registry checks (USB storage policy). No external baseline
is required; the controls reflect common Windows endpoint hardening guidance.
"""
from __future__ import annotations

from app.services.scanners.base import ps_json, safe_scan

# severity weight subtracted from 100 per failing control.
_WEIGHT = {"critical": 20, "high": 12, "medium": 8, "low": 4}


def _usb_storage_policy() -> bool | None:
    """USBSTOR Start value: 4 = USB mass-storage disabled (policy enforced)."""
    val = ps_json(
        "(Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\USBSTOR' "
        "-Name Start -ErrorAction SilentlyContinue).Start | ConvertTo-Json -Compress",
        timeout=10.0,
    )
    if val is None:
        return None
    try:
        return int(val) == 4
    except (TypeError, ValueError):
        return None


def _control(name: str, ok: bool | None, severity: str, pass_detail: str, fail_detail: str) -> dict:
    if ok is None:
        status = "not_evaluated"
        detail = "Could not determine (insufficient data or permissions)."
    elif ok:
        status = "pass"
        detail = pass_detail
    else:
        status = "fail"
        detail = fail_detail
    return {"name": name, "status": status, "severity": severity, "detail": detail}


@safe_scan("compliance")
def build(sections: dict) -> dict:
    security = sections.get("security") or {}
    os_ = sections.get("operating_system") or {}
    accounts = security.get("local_accounts") or {}

    bitlocker = (security.get("bitlocker") or {}).get("system_drive_protected")
    av = security.get("protection_active")
    fw = (security.get("firewall") or {}).get("all_enabled")
    pending = (os_.get("updates") or {}).get("pending_count")
    updates_ok = (pending == 0) if isinstance(pending, (int, float)) else None
    no_pwd = accounts.get("accounts_without_password")
    pwd_ok = (len(no_pwd) == 0) if isinstance(no_pwd, list) else None
    admin_count = accounts.get("administrator_count")
    admin_ok = (admin_count <= 2) if isinstance(admin_count, (int, float)) else None
    uac = (security.get("uac") or {}).get("enabled")
    secure_boot = (security.get("secure_boot") or {}).get("enabled")
    smb1 = (security.get("remote_access") or {}).get("smb1_enabled")
    usb_locked = _usb_storage_policy()

    controls = [
        _control("Disk encryption (BitLocker)", bitlocker, "critical",
                 "System drive is encrypted.", "System drive is not encrypted."),
        _control("Antivirus protection", av, "critical",
                 "Active real-time protection present.", "No active antivirus/real-time protection."),
        _control("Firewall enabled", fw, "high",
                 "All firewall profiles enabled.", "One or more firewall profiles disabled."),
        _control("Windows updates", updates_ok, "high",
                 "No pending updates.", f"{pending} update(s) pending."),
        _control("Account passwords", pwd_ok, "critical",
                 "All enabled accounts have passwords.",
                 f"{len(no_pwd) if isinstance(no_pwd, list) else '?'} account(s) without a password."),
        _control("Administrator accounts", admin_ok, "medium",
                 "Administrator count within policy.",
                 f"{admin_count} administrator accounts (review for least-privilege)."),
        _control("User Account Control (UAC)", uac, "medium",
                 "UAC is enabled.", "UAC is disabled."),
        _control("Secure Boot", secure_boot, "medium",
                 "Secure Boot is enabled.", "Secure Boot is disabled."),
        _control("SMBv1 disabled", (smb1 is False) if smb1 is not None else None, "high",
                 "Legacy SMBv1 is disabled.", "Legacy SMBv1 is enabled (attack vector)."),
        _control("USB storage policy", usb_locked, "low",
                 "USB mass-storage is restricted by policy.",
                 "USB mass-storage is allowed (no removable-media policy)."),
    ]

    evaluated = [c for c in controls if c["status"] != "not_evaluated"]
    failed = [c for c in controls if c["status"] == "fail"]
    score = 100
    for c in failed:
        score -= _WEIGHT.get(c["severity"], 8)
    score = max(0, min(100, score))

    return {
        "score": score,
        "status": "Compliant" if score >= 80 else ("Partial" if score >= 50 else "Non-compliant"),
        "controls": controls,
        "evaluated_count": len(evaluated),
        "passed_count": sum(1 for c in evaluated if c["status"] == "pass"),
        "failed_count": len(failed),
        "available": True,
    }
