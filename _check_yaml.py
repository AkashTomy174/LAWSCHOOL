"""Temporary YAML validation helper (deleted after use)."""

import sys

import yaml

for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    print(f"{path}: valid YAML")
    if "jobs" in data:
        for job, spec in data["jobs"].items():
            steps = spec.get("steps", [])
            print(f"  job '{job}': {len(steps)} steps, runs-on={spec.get('runs-on')}")
    if "services" in data:
        print(f"  services: {sorted(data['services'])}")
