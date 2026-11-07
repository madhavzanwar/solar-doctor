"""Telemetry x photo fusion engine (pure, DB-free). Decision table lives in rules.yaml."""
from .engine import fuse, load_rules
from .models import CLASSES, FusionSettings, FusionVerdict, PhotoEvidence, Severity, TelemetryEvidence

__all__ = ["CLASSES", "FusionSettings", "FusionVerdict", "PhotoEvidence", "Severity", "TelemetryEvidence",
           "fuse", "load_rules"]
