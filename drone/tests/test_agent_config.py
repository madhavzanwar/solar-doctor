# drone/tests/test_agent_config.py
from drone.agent.config import AgentConfig


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("DRONE_ID", "sitl-01")
    monkeypatch.setenv("DRONE_TOKEN", "dtok")
    monkeypatch.setenv("RELAY_WS_URL", "wss://relay.example.com")
    monkeypatch.setenv("MAVLINK_URL", "udpin:127.0.0.1:14550")
    monkeypatch.setenv("TELEMETRY_HZ", "5")

    cfg = AgentConfig.from_env()
    assert cfg.drone_id == "sitl-01"
    assert cfg.relay_ws_url == "wss://relay.example.com"
    assert cfg.ops_url() == "wss://relay.example.com/ws/drone/sitl-01?token=dtok"
    assert cfg.period_s == 0.2


def test_ops_url_percent_encodes_token_and_id(monkeypatch):
    monkeypatch.setenv("DRONE_ID", "site a/01")
    monkeypatch.setenv("DRONE_TOKEN", "a+b&c=d")
    monkeypatch.setenv("RELAY_WS_URL", "wss://relay.example.com")
    monkeypatch.setenv("MAVLINK_URL", "udpin:127.0.0.1:14550")
    cfg = AgentConfig.from_env()
    # special chars are escaped so the query param can't be truncated/mangled
    assert cfg.ops_url() == (
        "wss://relay.example.com/ws/drone/site%20a%2F01?token=a%2Bb%26c%3Dd"
    )


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("TELEMETRY_HZ", raising=False)
    monkeypatch.setenv("DRONE_ID", "x")
    monkeypatch.setenv("DRONE_TOKEN", "y")
    monkeypatch.setenv("RELAY_WS_URL", "wss://r")
    monkeypatch.setenv("MAVLINK_URL", "udpin:0.0.0.0:14550")
    cfg = AgentConfig.from_env()
    assert cfg.telemetry_hz == 5.0  # default
