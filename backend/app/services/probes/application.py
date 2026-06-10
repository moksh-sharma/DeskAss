"""Application live probe pack.

For a named app (e.g. Outlook, Teams, Chrome), checks whether it's running and
scans the Application event log for recent crash/hang events for that app."""
from __future__ import annotations

import psutil

from app.models.schemas import ProbeCheck, ProbeResult, Severity, TroubleshooterFinding
from app.services.probes.base import (
    IS_WINDOWS,
    ProbeContext,
    ProbeOutcome,
    as_list,
    ps_json,
)

DOMAIN = "application"
TITLE = "Application"

# App display name -> main executable base names (without .exe).
# Only an exact base-name match counts as "running" - background helpers
# (crash handlers, updaters, etc.) are reported separately.
# Note: the "new Outlook" for Windows runs as olk.exe (not outlook.exe).
_APP_PROCESS = {
    "Outlook": ["outlook", "olk"],
    "Microsoft Teams": ["teams", "ms-teams"],
    "Microsoft Word": ["winword"],
    "Microsoft Excel": ["excel"],
    "Microsoft Office": ["winword", "excel", "outlook", "olk"],
    "Google Chrome": ["chrome"],
    "Microsoft Edge": ["msedge"],
    "Mozilla Firefox": ["firefox"],
    "Brave": ["brave"],
    "Zoom": ["zoom"],
    "OneDrive": ["onedrive"],
    "Cursor": ["cursor"],
    "Visual Studio Code": ["code"],
    "Docker": ["docker", "com.docker.backend"],
    "Slack": ["slack"],
}

# Substrings in a process base name that indicate a background/helper, not the app itself.
_HELPER_PATTERNS = (
    "crashhandler", "crashpad", "crashreporter", "updater", "update",
    "installer", "setup", "broker", "helper", "gpu-process", "utility",
    "notification", "elevation", "launch", "silent", "watcher",
)

# Symptoms that mean "the app won't launch / is failing".
_LAUNCH_FAIL_SYMPTOMS = {"wont_start", "crash", "not_working", "not_detected"}

# App-specific safe-mode / repair hints.
_SAFE_MODE_HINT = {
    "Outlook": "`outlook.exe /safe`",
    "Microsoft Word": "`winword.exe /safe`",
    "Microsoft Excel": "`excel.exe /safe`",
}


def _launch_steps(app: str) -> list[str]:
    steps = [
        f"Fully close {app}: open Task Manager (Ctrl+Shift+Esc), end any lingering "
        f"'{app}' / background process, then launch it again.",
    ]
    safe = _SAFE_MODE_HINT.get(app)
    if safe:
        steps.append(f"Start {app} in safe mode to rule out add-ins: press Win+R and run {safe}.")
    steps += [
        f"Repair {app}: Settings > Apps > Installed apps > {app} > Modify/Advanced options > Repair.",
        "Restart the PC and try opening it again (clears stuck processes).",
        f"Check for {app} updates; if it still won't open, reinstall it.",
    ]
    if app == "Outlook":
        steps.append(
            "If only Outlook is affected, create a fresh mail profile: Control Panel > Mail > "
            "Show Profiles > Add, then set it as default (a corrupt profile is a common cause)."
        )
    return steps


def _process_base(name: str) -> str:
    n = (name or "").lower().strip()
    return n[:-4] if n.endswith(".exe") else n


def _normalize_keyword(keyword: str) -> str:
    return keyword.lower().removesuffix(".exe")


def _is_helper_process(base: str) -> bool:
    return any(h in base for h in _HELPER_PATTERNS)


def _iter_process_names() -> set[str]:
    names: set[str] = set()
    for p in psutil.process_iter(["name"]):
        try:
            n = (p.info.get("name") or "").strip().lower()
            if n:
                names.add(n)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return names


def _classify_processes(
    keywords: list[str],
    process_names: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (main_processes, background_helpers) for the given app keywords.

    Main = exact executable base-name match (e.g. brave.exe for keyword 'brave').
    Background = related helper processes (crash handlers, updaters, etc.) that
    must NOT be treated as the app being open.
    """
    norms = [_normalize_keyword(k) for k in keywords]
    names = process_names if process_names is not None else _iter_process_names()
    main: list[str] = []
    background: list[str] = []
    for n in sorted(names):
        base = _process_base(n)
        if not any(norm in base for norm in norms):
            continue
        if _is_helper_process(base):
            background.append(n)
        elif base in norms:
            main.append(n)
    return main, background


def _installed_match(app: str, keywords: list[str], installed_apps: list) -> object | None:
    """Find an installed-app inventory entry matching the named app."""
    app_l = app.lower()
    for ia in installed_apps or []:
        name_l = (getattr(ia, "name", "") or "").lower()
        if app_l in name_l or any(k in name_l for k in keywords):
            return ia
    return None


def _crash_events(keywords: list[str]) -> list[dict]:
    if not IS_WINDOWS:
        return []
    # Application Error (1000) / App Hang (1002) / .NET (1026) carry the faulting module.
    data = as_list(ps_json(
        "Get-WinEvent -FilterHashtable @{LogName='Application'; Level=2; Id=1000,1002,1026} "
        "-MaxEvents 40 -ErrorAction SilentlyContinue | "
        "Select-Object Id,ProviderName,TimeCreated,Message | ConvertTo-Json -Compress",
        timeout=25.0,
    ))
    out = []
    for e in data:
        msg = str(e.get("Message", "")).lower()
        if any(k in msg for k in keywords):
            out.append(e)
    return out


def investigate(ctx: ProbeContext) -> ProbeOutcome:
    checks: list[ProbeCheck] = []
    findings: list[TroubleshooterFinding] = []

    apps = ctx.apps or []
    if not apps:
        return ProbeOutcome(
            result=ProbeResult(domain=DOMAIN, title=TITLE, available=True,
                               note="No specific application named.", checks=checks),
            findings=findings,
        )

    for app in apps:
        keywords = _APP_PROCESS.get(app, [app.split()[0].lower()])
        running, background = _classify_processes(keywords, ctx.process_names)
        checks.append(ProbeCheck(
            label=f"{app} running",
            value=("Yes" if running else "No") + (f" ({', '.join(running)})" if running else ""),
            status=Severity.healthy if running else Severity.info,
        ))
        if background:
            checks.append(ProbeCheck(
                label=f"{app} background processes",
                value=", ".join(background),
                status=Severity.info,
                detail="Background helpers only - not counted as the app being open.",
            ))

        # Installed? (from the live inventory)
        installed = _installed_match(app, keywords, ctx.installed_apps)
        if installed is not None:
            ver = getattr(installed, "version", None)
            checks.append(ProbeCheck(
                label=f"{app} installed",
                value=f"Yes" + (f" (v{ver})" if ver else ""),
                status=Severity.healthy,
            ))
        elif ctx.installed_apps:
            # Inventory present but app not found - it may not be installed.
            checks.append(ProbeCheck(
                label=f"{app} installed",
                value="Not found in installed apps",
                status=Severity.warning,
            ))
            findings.append(TroubleshooterFinding(
                id=f"app_not_installed_{app.lower().replace(' ', '_')}",
                title=f"{app} May Not Be Installed",
                area="Applications",
                severity=Severity.warning,
                detected=f"{app} was not found in the list of installed applications on this PC.",
                likely_cause="The app isn't installed (or was uninstalled / installed only for another user).",
                resolution_steps=[
                    f"Confirm {app} is installed: Settings > Apps > Installed apps and search for it.",
                    f"If missing, download and reinstall {app} from the official source.",
                    "If it was installed per-user, reinstall it for your current Windows account.",
                ],
                ask_ai_prompt=f"{app} doesn't seem to be installed on this PC. How do I install/restore it?",
            ))

        crashes = _crash_events(keywords)
        if crashes:
            checks.append(ProbeCheck(
                label=f"{app} crash/hang events",
                value=str(len(crashes)),
                status=Severity.warning,
                detail=str(crashes[0].get("Message", ""))[:140],
            ))
            findings.append(TroubleshooterFinding(
                id=f"app_crashes_{app.lower().replace(' ', '_')}",
                title=f"{app} Is Crashing or Hanging",
                area="Applications",
                severity=Severity.warning,
                detected=f"{len(crashes)} recent crash/hang event(s) for {app} in the Application log.",
                likely_cause="A corrupt profile/cache, a faulty add-in/extension, or a missing runtime.",
                resolution_steps=[
                    f"Update {app} fully and restart the PC.",
                    f"Start {app} in safe mode to rule out add-ins (e.g. `outlook.exe /safe` for Outlook).",
                    f"Repair {app}: Settings > Apps > Installed apps > {app} > Modify/Advanced > Repair.",
                    "Disable add-ins/extensions, then re-enable one at a time to find the culprit.",
                    "Clear the app's cache; test in a new Windows user profile to rule out profile corruption.",
                ],
                ask_ai_prompt=f"{app} keeps crashing on this PC. What is the likely cause and how do I fix it?",
            ))
        else:
            checks.append(ProbeCheck(
                label=f"{app} crash/hang events",
                value="None recent",
                status=Severity.healthy,
            ))

        launch_issue = bool(set(ctx.symptoms) & _LAUNCH_FAIL_SYMPTOMS)

        # App IS running but the user says it "won't open" - it's likely hung,
        # minimized to the tray, or open on another desktop with no visible window.
        if running and launch_issue and not crashes:
            findings.append(TroubleshooterFinding(
                id=f"app_running_no_window_{app.lower().replace(' ', '_')}",
                title=f"{app} Is Already Running (No Visible Window)",
                area="Applications",
                severity=Severity.warning,
                detected=f"{app} is running ({', '.join(running)}) but you reported it won't open - "
                "it's likely hung or has no visible window.",
                likely_cause="The app is stuck in the background, minimized to the system tray, or its "
                "window opened off-screen / on another virtual desktop.",
                resolution_steps=[
                    f"Press Alt+Tab to look for an open {app} window; check the system tray (bottom-right arrow).",
                    f"Force-close it: Task Manager (Ctrl+Shift+Esc) > select all '{app}' processes > End task.",
                    f"Relaunch {app} and wait ~30 seconds for the window to appear.",
                    *( [f"If it hangs again, start it in safe mode: Win+R > {_SAFE_MODE_HINT[app]}."]
                       if app in _SAFE_MODE_HINT else [] ),
                    f"If it still won't show a window, repair {app}: Settings > Apps > Installed apps > "
                    f"{app} > Modify/Advanced options > Repair, then restart the PC.",
                ],
                ask_ai_prompt=f"{app} is running in the background but no window opens. How do I fix it?",
            ))

        # The user reported a launch/crash problem and the app isn't running with
        # no logged crash - give actionable launch troubleshooting instead of
        # concluding "no fault". (Apps that crash on launch often log nothing.)
        if not running and not crashes and launch_issue:
            detected = (
                f"{app} is not currently running"
                + (f" (only background helpers: {', '.join(background)})" if background else "")
                + " and no crash was logged - it likely fails or exits silently on launch."
            )
            findings.append(TroubleshooterFinding(
                id=f"app_wont_open_{app.lower().replace(' ', '_')}",
                title=f"{app} Is Not Running / Won't Open",
                area="Applications",
                severity=Severity.warning,
                detected=detected,
                likely_cause="A stuck background process, a faulty add-in/extension, a corrupt profile or "
                "cache, or a pending update is preventing the app from opening.",
                resolution_steps=_launch_steps(app),
                ask_ai_prompt=f"{app} won't open on this PC - nothing happens when I launch it. How do I fix it?",
            ))

    return ProbeOutcome(
        result=ProbeResult(domain=DOMAIN, title=TITLE, available=True, checks=checks),
        findings=findings,
    )
