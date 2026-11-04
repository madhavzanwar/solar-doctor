# drone/tests/test_video_pipeline.py
from drone.agent.video_pipeline import build_video_pipeline


def test_webcam_pipeline_uses_device_and_hardware_encode():
    p = build_video_pipeline(name="rgb", device="/dev/video0",
                             bitrate_bps=4_000_000, use_test_pattern=False)
    assert "v4l2src" in p
    assert "/dev/video0" in p
    assert "nvv4l2h264enc" in p          # Orin hardware H.264
    assert "rtph264pay" in p
    assert "webrtcbin" in p
    assert "name=rgb" in p


def test_test_pattern_pipeline_has_no_device():
    p = build_video_pipeline(name="rgb", device="/dev/video0",
                             bitrate_bps=2_000_000, use_test_pattern=True)
    assert "videotestsrc" in p
    assert "v4l2src" not in p


def test_bitrate_is_embedded():
    p = build_video_pipeline(name="thermal", device="/dev/video1",
                             bitrate_bps=1_500_000, use_test_pattern=False)
    assert "1500000" in p
