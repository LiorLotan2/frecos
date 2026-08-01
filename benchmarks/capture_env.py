"""Captures the hardware/OS/interpreter environment an experiment ran on, into
env.json next to that experiment's results.csv. The report's peak_rss_mb and CPU%
columns are explicitly flagged there as unreliable on a shared machine; this makes
"was this run on a shared or dedicated machine" at least answerable rather than
implicit.
"""
import json
import os
import platform
import subprocess
import sys

import psutil


def _cpu_model() -> str:
    if platform.system() == "Darwin":
        try:
            return subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            return "unknown"
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
    return platform.processor() or "unknown"


def capture() -> dict:
    return {
        "cpu_model": _cpu_model(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_total_bytes": psutil.virtual_memory().total,
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python_version": sys.version,
    }


def write_env_json(results_dir: str) -> None:
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, "env.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(capture(), f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    print(json.dumps(capture(), indent=2, sort_keys=True))
