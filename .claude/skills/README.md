# Axalon Skills

Per-feature reference skills for Claude Code (auto-discovered) and any agent (read directly). Each `SKILL.md` has YAML frontmatter (`name`, `description`) and tells you **what the feature is, where it lives, how to work on it, and the gotchas**.

| Skill | Feature |
|-------|---------|
| [ml-detection](ml-detection/SKILL.md) | YOLO11m thermal anomaly detection — classes, severity, detection dicts |
| [platform-api](platform-api/SKILL.md) | FastAPI backend — endpoints, auth, conventions |
| [analysis-pipeline](analysis-pipeline/SKILL.md) | ingest → detect → report orchestration |
| [park-localization](park-localization/SKILL.md) | panel numbering + GPS anchoring (OCR / auto-grid) |
| [reporting](reporting/SKILL.md) | PDF / Excel / GeoJSON report generation |
| [database](database/SKILL.md) | SQLAlchemy models, Alembic, SQLite↔Postgres |
| [mission-planner](mission-planner/SKILL.md) | drone mission planning + waypoint export |
| [website-3d](website-3d/SKILL.md) | scroll-driven React Three Fiber scene |
| [cloud-deployment](cloud-deployment/SKILL.md) | Vercel + HF Spaces + Supabase deployment |

Start with `../../AGENTS.md` for rules/commands and `../../docs/CODEMAP.md` for the architecture map.
