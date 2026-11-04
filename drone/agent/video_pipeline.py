# drone/agent/video_pipeline.py
"""GStreamer pipeline strings for WebRTC video on the Jetson Orin.

Hardware-encodes H.264 via NVENC (`nvv4l2h264enc`) and feeds a named `webrtcbin`.
`use_test_pattern=True` swaps the camera for `videotestsrc` so the WebRTC path is
demoable with no hardware. Pure string construction — no GStreamer import here.
"""
from __future__ import annotations


def build_video_pipeline(
    *, name: str, device: str, bitrate_bps: int, use_test_pattern: bool
) -> str:
    if use_test_pattern:
        source = "videotestsrc is-live=true pattern=ball"
    else:
        source = f"v4l2src device={device}"
    return (
        f"webrtcbin name={name} "
        f"{source} ! videoconvert ! nvvidconv ! "
        f"nvv4l2h264enc bitrate={bitrate_bps} insert-sps-pps=true ! "
        f"h264parse ! rtph264pay config-interval=1 pt=96 ! "
        f"application/x-rtp,media=video,encoding-name=H264,payload=96 ! {name}."
    )
