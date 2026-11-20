"""Check that every Hugging Face id used by the bake-off resolves; record sha + licence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from huggingface_hub import model_info

from ml.rgb.configs import hf_ids

OUT = Path(__file__).parent / "reports" / "hf_ids.json"


def main() -> int:
    ok, failed = {}, {}
    for mid in hf_ids():
        try:
            info = model_info(mid)
            lic = (info.card_data.license if info.card_data else None) or next(
                (t.split(":", 1)[1] for t in info.tags if t.startswith("license:")), None)
            ok[mid] = {"sha": info.sha, "license": lic}
        except Exception as exc:  # report every failure, suggest nothing
            failed[mid] = f"{type(exc).__name__}: {exc}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"resolved": ok, "failed": failed}, indent=2))
    for mid, err in failed.items():
        print(f"FAILED {mid}: {err}", file=sys.stderr)
    print(f"{len(ok)} resolved, {len(failed)} failed -> {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
