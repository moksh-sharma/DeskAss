"""Developer environment scanner — toolchains, IDEs, containers (quick probe)."""
from __future__ import annotations

import os
import shutil

from app.services.probes.base import run_powershell
from app.services.scanners.base import safe_scan


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _version(cmd: str, args: str = "--version") -> str | None:
    try:
        out = run_powershell(f"& '{cmd}' {args} 2>$null | Select-Object -First 1", timeout=8.0)
        return (out or "").strip()[:120] or None
    except Exception:
        return None


@safe_scan("dev_environment")
def scan() -> dict:
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")

    tools: dict[str, dict] = {}

    def add(name: str, installed: bool, version: str | None = None, path: str | None = None) -> None:
        tools[name] = {"installed": installed, "version": version, "path": path}

    git = _which("git")
    add("git", bool(git), _version(git) if git else None, git)
    node = _which("node")
    add("node", bool(node), _version(node) if node else None, node)
    npm = _which("npm")
    add("npm", bool(npm), _version(npm) if npm else None, npm)
    python = _which("python") or _which("python3")
    add("python", bool(python), _version(python) if python else None, python)
    docker = _which("docker")
    add("docker", bool(docker), _version(docker) if docker else None, docker)
    kubectl = _which("kubectl")
    add("kubernetes", bool(kubectl), _version(kubectl, "version --client") if kubectl else None, kubectl)
    java = _which("java")
    add("java", bool(java), _version(java) if java else None, java)
    mvn = _which("mvn")
    add("maven", bool(mvn), _version(mvn) if mvn else None, mvn)
    gradle = _which("gradle")
    add("gradle", bool(gradle), _version(gradle) if gradle else None, gradle)
    conda = _which("conda")
    add("conda", bool(conda), _version(conda) if conda else None, conda)

    wsl = run_powershell("wsl --status 2>$null | Select-Object -First 3", timeout=10.0)
    add("wsl", bool(wsl and "not" not in wsl.lower()[:40]), wsl[:80] if wsl else None)

    code_paths = [
        os.path.join(local, "Programs", "Microsoft VS Code"),
        os.path.join(home, ".vscode"),
    ]
    cursor_paths = [
        os.path.join(local, "Programs", "cursor"),
        os.path.join(home, ".cursor"),
    ]
    add("vscode", any(os.path.exists(p) for p in code_paths))
    add("cursor", any(os.path.exists(p) for p in cursor_paths))

    installed = [k for k, v in tools.items() if v.get("installed")]
    return {
        "tools": tools,
        "installed_count": len(installed),
        "installed_tools": installed,
        "available": True,
    }
