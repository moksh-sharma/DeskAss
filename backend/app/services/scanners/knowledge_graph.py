"""Knowledge graph: links the entities the scan already discovered
(applications, processes, services, drivers, devices, errors) into a relationship
model used for root-cause, impact and dependency analysis.

Pure synthesis over the assembled sections - deterministic, no model.
"""
from __future__ import annotations

from app.services.scanners.base import safe_scan

_MAX_PROC_NODES = 60


def _node(nid: str, ntype: str, label: str) -> dict:
    return {"id": nid, "type": ntype, "label": label}


@safe_scan("knowledge_graph")
def build(sections: dict) -> dict:
    processes = (sections.get("processes") or {})
    services = (sections.get("services") or {})
    drivers = (sections.get("drivers") or {})
    crash = (sections.get("crash_analysis") or {})
    devices = ((sections.get("hardware") or {}).get("devices") or {})

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    correlations: list[str] = []

    def add(nid, ntype, label):
        if nid not in nodes:
            nodes[nid] = _node(nid, ntype, label)
        return nid

    # --- Process tree (subset: heaviest + their parents) --------------------
    all_procs = processes.get("all_processes") or []
    by_pid = {p.get("pid"): p for p in all_procs if p.get("pid") is not None}
    subset = sorted(all_procs, key=lambda p: p.get("memory_mb") or 0, reverse=True)[:_MAX_PROC_NODES]
    subset_pids = {p.get("pid") for p in subset}
    for p in subset:
        pid = p.get("pid")
        add(f"proc:{pid}", "process", f"{p.get('name')} (pid {pid})")
        ppid = p.get("ppid")
        if ppid in subset_pids and ppid != pid:
            parent = by_pid.get(ppid)
            add(f"proc:{ppid}", "process", f"{parent.get('name')} (pid {ppid})")
            edges.append({"source": f"proc:{ppid}", "target": f"proc:{pid}", "relation": "spawned"})

    # --- Service -> hosting process -----------------------------------------
    proc_by_pid_name = {p.get("pid"): (p.get("name") or "") for p in all_procs}
    for s in (services.get("inventory") or []):
        pid = s.get("pid")
        if pid and pid in proc_by_pid_name:
            sid = add(f"svc:{s.get('name')}", "service", s.get("display_name") or s.get("name"))
            add(f"proc:{pid}", "process", f"{proc_by_pid_name[pid]} (pid {pid})")
            edges.append({"source": sid, "target": f"proc:{pid}", "relation": "hosted_by"})

    # --- Failed critical service -> dependents (impact analysis) ------------
    for m in (services.get("monitored") or []):
        if not m.get("issue"):
            continue
        sid = add(f"svc:{m.get('service')}", "service", m.get("name"))
        deps = (m.get("dependencies") or {}).get("dependent_services") or []
        for dep in deps[:8]:
            did = add(f"svc:{dep}", "service", dep)
            edges.append({"source": sid, "target": did, "relation": "required_by"})
        if deps:
            correlations.append(
                f"Service '{m.get('name')}' is not running and {len(deps)} dependent "
                f"service(s) rely on it: {', '.join(deps[:5])}."
            )
        else:
            correlations.append(f"Critical service '{m.get('name')}' is not running.")

    # --- Problem device -> driver -------------------------------------------
    for d in (devices.get("problem_devices") or [])[:12]:
        name = d.get("name") or "device"
        did = add(f"dev:{name}", "device", name)
        cls = d.get("class") or "driver"
        drid = add(f"driver:{cls}", "driver", f"{cls} driver")
        edges.append({"source": did, "target": drid, "relation": "needs_driver"})
        correlations.append(
            f"Device '{name}' reports a problem ({d.get('status') or 'error'}); "
            f"its {cls} driver is the likely fix."
        )

    # --- Driver problems (missing/failed) -----------------------------------
    for d in (drivers.get("problem_devices") or [])[:8]:
        name = d.get("name") or "device"
        add(f"dev:{name}", "device", name)

    # --- Crash app -> running process ---------------------------------------
    name_to_pid: dict[str, int] = {}
    for p in all_procs:
        nm = (p.get("name") or "").lower()
        if nm and nm not in name_to_pid:
            name_to_pid[nm] = p.get("pid")
    for c in (crash.get("application_crashes") or [])[:10]:
        app = (c.get("app") or c.get("name") or "").strip()
        if not app:
            continue
        eid = add(f"err:{app}", "error", f"Crash: {app}")
        key = app.lower()
        if not key.endswith(".exe"):
            key += ".exe"
        pid = name_to_pid.get(key)
        if pid is not None:
            add(f"proc:{pid}", "process", f"{app} (pid {pid})")
            edges.append({"source": eid, "target": f"proc:{pid}", "relation": "occurred_in"})
            correlations.append(f"App '{app}' crashed recently and is currently running (pid {pid}).")

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "correlations": correlations[:12],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "available": True,
    }
