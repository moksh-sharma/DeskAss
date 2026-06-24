"""AI / ML environment scanner — local LLM runtimes, model caches, GPU compute."""
from __future__ import annotations

import os
import shutil

from app.services.probes.base import run_powershell
from app.services.scanners.base import safe_scan


@safe_scan("ai_environment")
def scan() -> dict:
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")

    stacks: dict[str, dict] = {}

    def add(name: str, installed: bool, detail: str | None = None, path: str | None = None) -> None:
        stacks[name] = {"installed": installed, "detail": detail, "path": path}

    ollama = shutil.which("ollama")
    if ollama:
        ver = run_powershell("ollama --version 2>$null", timeout=8.0)
        add("ollama", True, (ver or "").strip()[:80], ollama)
    else:
        ollama_dir = os.path.join(home, ".ollama")
        add("ollama", os.path.isdir(ollama_dir), "models dir present" if os.path.isdir(ollama_dir) else None, ollama_dir)

    lmstudio = os.path.join(local, "LM Studio")
    add("lm_studio", os.path.isdir(lmstudio), None, lmstudio if os.path.isdir(lmstudio) else None)

    hf_cache = os.path.join(home, ".cache", "huggingface")
    add("huggingface_cache", os.path.isdir(hf_cache), None, hf_cache if os.path.isdir(hf_cache) else None)

    torch_cache = os.path.join(home, ".cache", "torch")
    add("pytorch_cache", os.path.isdir(torch_cache), None, torch_cache if os.path.isdir(torch_cache) else None)

    cuda = run_powershell("nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>$null", timeout=10.0)
    add("cuda_nvidia", bool(cuda and "nvidia" in cuda.lower()), cuda[:120] if cuda else None)

    rocm = shutil.which("rocminfo")
    add("rocm", bool(rocm), None, rocm)

    installed = [k for k, v in stacks.items() if v.get("installed")]
    return {
        "stacks": stacks,
        "installed_count": len(installed),
        "installed_stacks": installed,
        "available": True,
    }
