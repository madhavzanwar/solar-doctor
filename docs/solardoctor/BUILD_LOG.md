# Build log (Prompt 1: foundation)

- Phase A: merged `Parakh20/AxalonSystems@main` with full history. Baseline: 632 pass / 10 fail (need weights). See `BASELINE_TESTS.md`.
  - **Blocked:** LFS `best.pt` cannot be fetched (git proxy denies Parakh20/AxalonSystems LFS) and no `HF_TOKEN` -> HF upload not done. `scripts/publish_weights_hf.py` is ready; thermal stays `ENABLE_THERMAL=false`.
- Phase B: six agents in `.claude/agents/`.
- Phase C: package rename, `ml/` and `website/nextjs` moves, `/api/v1` mounting, Makefile, notices. Parity kept.
