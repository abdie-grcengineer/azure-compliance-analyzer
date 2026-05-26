"""
CMMC L2 mapper. Maps a Defender for Cloud assessment to one or more
CMMC Level 2 practice IDs.

CMMC Level 2 enforces the 110 practices from NIST SP 800-171 Rev 2. Practice
IDs are formatted like `AC.L2-3.1.1` (domain.level-NIST-id). The mapping
JSON lives in config/mappings/cmmc.json and uses simple keyword matches on
the assessment title to suggest practices.

v1 keeps the surface tiny on purpose. The full mapper (weighted keyword
scoring, domain rollups, scoring per CMMC assessment guide) is a v2 task.
"""

import json
import os
from pathlib import Path
from typing import Any


class CMMCMapper:
    def __init__(self, mapping_path: str | None = None):
        default_path = Path(__file__).parent.parent / "config" / "mappings" / "cmmc.json"
        path = Path(mapping_path or os.environ.get("CMMC_MAPPING_PATH", str(default_path)))
        with open(path) as f:
            self._mapping = json.load(f)

    def map_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        title = (finding.get("Title") or "").lower()
        practices: list[str] = []
        for entry in self._mapping["keywords"]:
            if any(kw.lower() in title for kw in entry["match"]):
                practices.extend(entry["practices"])

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique = [p for p in practices if not (p in seen or seen.add(p))]

        return {
            **finding,
            "CMMCPractices": unique or ["UNMAPPED"],
            "CMMCDomains": sorted({p.split(".")[0] for p in unique if p != "UNMAPPED"}),
        }
