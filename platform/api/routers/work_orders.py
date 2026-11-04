"""work_orders router — CSV / XLSX export of a park's actionable faults for O&M crews."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter

from axalon.api.deps import *  # noqa: F401,F403
from axalon.core.fault_workflow import (
    ACTIONABLE_STATUSES,
    PRIORITY_RANK,
    derived_priority,
    effective_priority,
)

router = APIRouter(tags=["work-orders"])

WORK_ORDER_COLUMNS = (
    "fault_id", "panel_id", "lat", "lon", "class", "severity", "priority",
    "status", "assignee", "due_date", "first_seen", "last_seen", "occurrences",
    "notes",
)

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Leading characters spreadsheet apps treat as a formula (CSV/formula injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _parse_statuses(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return ACTIONABLE_STATUSES
    statuses = tuple(dict.fromkeys(s.strip() for s in raw.split(",") if s.strip()))
    invalid = [s for s in statuses if s not in FAULT_STATUSES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status {', '.join(invalid)}. Allowed: {', '.join(FAULT_STATUSES)}",
        )
    return statuses


def _gps(fault: PanelFault) -> tuple[float | None, float | None]:
    if not fault.last_gps:
        return None, None
    try:
        gps = json.loads(fault.last_gps)
        return float(gps["lat"]), float(gps["lon"])
    except (ValueError, TypeError, KeyError):
        return None, None


def _row(fault: PanelFault) -> dict:
    lat, lon = _gps(fault)
    return {
        "fault_id": fault.id,
        "panel_id": fault.panel_id,
        "lat": lat,
        "lon": lon,
        "class": fault.class_,
        "severity": fault.severity,
        "priority": effective_priority(fault),
        "status": fault.status,
        "assignee": fault.assignee,
        "due_date": fault.due_date.isoformat() if fault.due_date else None,
        "first_seen": fault.first_seen_date,
        "last_seen": fault.last_seen_date,
        "occurrences": fault.occurrences,
        "notes": fault.notes,
    }


def _sort_key(fault: PanelFault) -> tuple:
    priority = effective_priority(fault) or derived_priority(fault)
    return (
        PRIORITY_RANK.get(priority or "", len(PRIORITY_RANK)),
        fault.due_date or date.max,
        fault.panel_id or "",
        fault.id,
    )


def _neutralise(value):
    """Prefix text that a spreadsheet would evaluate as a formula."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _to_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=WORK_ORDER_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else _neutralise(v)) for k, v in row.items()})
    return buf.getvalue().encode("utf-8")


def _to_xlsx(rows: list[dict], park_id: str) -> bytes:
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Work orders"
    ws.append(list(WORK_ORDER_COLUMNS))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([_neutralise(row[col]) for col in WORK_ORDER_COLUMNS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.properties.title = f"{park_id} work orders"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@router.get("/parks/{park_id}/work-orders")
def export_work_orders(
    park_id: str,
    format: str = "csv",
    status: str | None = None,
    assignee: str | None = None,
    principal: Principal = Depends(current_principal),
):
    """Download a park's work orders.

    - `format`: csv | xlsx
    - `status`: comma-separated statuses (default open,assigned,in_progress)
    - `assignee`: case-insensitive exact match
    """
    ensure_park_visible(principal, park_id)
    park_id = _validate_park_id(park_id)
    fmt = (format or "").strip().lower()
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(status_code=400, detail="format must be csv or xlsx")
    statuses = _parse_statuses(status)
    session = get_session()
    try:
        if session.query(Park).filter_by(id=park_id).first() is None:
            raise HTTPException(status_code=404, detail="Park not found")
        q = session.query(PanelFault).filter(
            PanelFault.park_id == park_id, PanelFault.status.in_(statuses)
        )
        wanted_assignee = (assignee or "").strip().lower()
        faults = [
            f for f in q.all()
            if not wanted_assignee or (f.assignee or "").strip().lower() == wanted_assignee
        ]
        rows = [_row(f) for f in sorted(faults, key=_sort_key)]
    finally:
        session.close()

    stamp = datetime.utcnow().strftime("%Y%m%d")
    filename = f"{park_id}_work_orders_{stamp}.{fmt}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if fmt == "xlsx":
        return Response(content=_to_xlsx(rows, park_id), media_type=_XLSX_MEDIA_TYPE, headers=headers)
    return Response(content=_to_csv(rows), media_type="text/csv; charset=utf-8", headers=headers)
