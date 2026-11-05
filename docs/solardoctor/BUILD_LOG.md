# Build log (Prompt 1: foundation)

- Phase A: merged `Parakh20/AxalonSystems@main` with full history. Baseline: 632 pass / 10 fail (need weights). See `BASELINE_TESTS.md`.
  - **Blocked:** LFS `best.pt` cannot be fetched (git proxy denies Parakh20/AxalonSystems LFS) and no `HF_TOKEN` -> HF upload not done. `scripts/publish_weights_hf.py` is ready; thermal stays `ENABLE_THERMAL=false`.
- Phase B: six agents in `.claude/agents/`.
- Phase C: package rename, `ml/` and `website/nextjs` moves, `/api/v1` mounting, Makefile, notices. Parity kept.
- Phase E (sd-physics): SolarPulse physics/ML ported to `ml/forecast` + `backend/solardoctor/physics`, migration 0011, routers under `/api/v1`. See DECISIONS E1-E11.
  - **Note for sd-frontend (QA F3):** `DiagnosisModal.tsx` hard-codes a dollar sign (`$${...toFixed(2)}/day`). The API now returns `currency` (`"INR"` with a plant tariff, `"unset"` without) and `financial_assumption`. Render "not estimated" when `currency === "unset"` (the 0.0 is a placeholder) and use the currency symbol otherwise (INR = rupee sign). Diagnosis responses also carry `telemetry_ts` / `telemetry_source`; show a SIMULATED badge when `telemetry_source === "SIMULATED"`. `POST /diagnosis/diagnose` returns 422 with a `detail` reason when no acceptable telemetry exists: show it instead of a generic error.
