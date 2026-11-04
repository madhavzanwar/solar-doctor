# drone/relay/tier_policy.py
"""Link-tier command policy + authorization, enforced authoritatively on the relay.

Phase 2 commands are all "mission control" class: allowed on GREEN and AMBER,
blocked on RED (degraded link). Manual stick commands arrive in Phase 5 and will
be GREEN-only — this table is where that distinction will live.
"""
from __future__ import annotations

from drone.common.commands import CommandType
from drone.common.telemetry import LinkTier

# Mission-control command set (everything in Phase 2).
_MISSION_CONTROL: set[CommandType] = set(CommandType)

_ALLOWED: dict[LinkTier, set[CommandType]] = {
    LinkTier.GREEN: set(_MISSION_CONTROL),   # + manual in Phase 5
    LinkTier.AMBER: set(_MISSION_CONTROL),
    LinkTier.RED: set(),                       # degraded: block all
}


def is_allowed(tier: LinkTier, cmd_type: CommandType) -> bool:
    return cmd_type in _ALLOWED[tier]


def authorize_command(
    *, holds_lock: bool, tier: LinkTier, cmd_type: CommandType
) -> tuple[bool, str]:
    if not holds_lock:
        return False, "you do not hold the control lock"
    if not is_allowed(tier, cmd_type):
        return False, f"{cmd_type.value} not allowed at link tier {tier.value}"
    return True, ""


def authorize_manual(*, holds_lock: bool, tier: LinkTier) -> tuple[bool, str]:
    """Manual stick input is GREEN-only (low-latency link) and holder-only."""
    if not holds_lock:
        return False, "you do not hold the control lock"
    if tier is not LinkTier.GREEN:
        return False, f"manual control requires a GREEN link (current: {tier.value})"
    return True, ""
