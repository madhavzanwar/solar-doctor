"""Regenerate golden/solarpulse_golden.json from the ORIGINAL SolarPulseAI code.

Usage (needs the SolarPulseAI clone, see sp_original.py):
    PYTHONSAFEPATH=1 PYTHONPATH=backend:.:tests/backend/physics python tests/backend/physics/make_golden.py
"""
import json
from pathlib import Path

import golden_cases

if __name__ == "__main__":
    data = golden_cases.run_cases(golden_cases.original())
    path = Path(__file__).parent / "golden" / "solarpulse_golden.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True))
    print("wrote", path, len(data), "cases")
