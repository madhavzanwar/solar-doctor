# drone/agent/config.py
"""Agent configuration from environment. No secrets in code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class AgentConfig:
    drone_id: str
    drone_token: str
    relay_ws_url: str   # base, e.g. wss://relay.example.com
    mavlink_url: str    # e.g. udpin:127.0.0.1:14550 (SITL)
    telemetry_hz: float
    min_alt_m: float
    max_alt_m: float
    heartbeat_hz: float
    deadman_timeout_s: float
    video_enabled: bool
    webcam_device: str
    thermal_device: str
    video_test_pattern: bool
    video_bitrate_bps: int
    manual_deadman_s: float
    recording_enabled: bool
    capture_dir: str
    park_id: str
    platform_api_url: str
    platform_token: str
    gps_tolerance_s: float

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            drone_id=os.environ["DRONE_ID"],
            drone_token=os.environ["DRONE_TOKEN"],
            relay_ws_url=os.environ["RELAY_WS_URL"].rstrip("/"),
            mavlink_url=os.environ["MAVLINK_URL"],
            telemetry_hz=float(os.getenv("TELEMETRY_HZ", "5")),
            min_alt_m=float(os.getenv("MIN_ALT_M", "5")),
            max_alt_m=float(os.getenv("MAX_ALT_M", "120")),
            heartbeat_hz=float(os.getenv("HEARTBEAT_HZ", "2")),
            deadman_timeout_s=float(os.getenv("DEADMAN_TIMEOUT_S", "5")),
            video_enabled=os.getenv("VIDEO_ENABLED", "1") == "1",
            webcam_device=os.getenv("WEBCAM_DEVICE", "/dev/video0"),
            thermal_device=os.getenv("THERMAL_DEVICE", "/dev/video1"),
            video_test_pattern=os.getenv("VIDEO_TEST_PATTERN", "0") == "1",
            video_bitrate_bps=int(os.getenv("VIDEO_BITRATE_BPS", "4000000")),
            manual_deadman_s=float(os.getenv("MANUAL_DEADMAN_S", "0.4")),
            recording_enabled=os.getenv("RECORDING_ENABLED", "0") == "1",
            capture_dir=os.getenv("CAPTURE_DIR", "/data/captures"),
            park_id=os.getenv("PARK_ID", ""),
            platform_api_url=os.getenv("PLATFORM_API_URL", ""),
            platform_token=os.getenv("PLATFORM_TOKEN", ""),
            gps_tolerance_s=float(os.getenv("GPS_TOLERANCE_S", "0.5")),
        )

    @property
    def period_s(self) -> float:
        return 1.0 / self.telemetry_hz

    def ops_url(self) -> str:
        drone_id = quote(self.drone_id, safe="")
        token = quote(self.drone_token, safe="")
        return f"{self.relay_ws_url}/ws/drone/{drone_id}?token={token}"
