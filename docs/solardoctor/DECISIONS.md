# Decisions

| # | Date | Decision | Why |
|---|---|---|---|
| 1 | 2026-11-04 | Python package renamed `axalon` -> `solardoctor` (kept, not reverted). | Backend suite is at exact parity with the Axalon baseline (632 pass, same 10 weight-dependent failures). `AXALON_*` env vars are mirrored to `SOLARDOCTOR_*` at import time. |
| 2 | 2026-11-04 | Work and push on branch `claude/practical-dirac-fddnwu`, not `main`. | The session is restricted to that branch; the prompt's "push to main + tag" is deferred to the user. |
| 3 | 2026-11-04 | `/api/v1` is canonical; unprefixed routes stay as hidden deprecated aliases. | Existing tests and the legacy Next.js site use unprefixed paths. |
| 4 | 2026-11-04 | `ml/` -> `ml/thermal/` (package `ml.thermal`). | Leaves room for `ml/rgb` and `ml/forecast`. |
| 5 | 2026-11-04 | Thermal weights are not in git; `scripts/fetch_weights.py` pulls from HF; `ENABLE_THERMAL=false` by default in `.env.example`. | The LFS object cannot be fetched from this sandbox and no `HF_TOKEN` is available; upload is pending. |
| 6 | 2026-11-04 | Stripped the `best.pt` LFS pointer (`ml/checkpoints/best.pt`) from local history with `git filter-branch` before the first push. Backup ref: local `backup/pre-lfs-strip`. | GitHub rejects pushes whose history references an LFS object the repo does not hold (GH008), and the prompt forbids pushing the weights into our LFS. All other Axalon history/authorship is preserved; commit hashes differ from upstream. |
