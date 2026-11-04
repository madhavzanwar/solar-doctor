# drone/agent/webrtc_publisher.py
"""WebRTC publisher: one webrtcbin pipeline per operator who requests video.

Glue over GStreamer. The agent receives an OFFER (SignalMsg) from an operator,
spins up a pipeline (webcam track), sets the remote description, creates an
ANSWER, and trickles ICE back via `send_signal`.

`send_signal(SignalMsg)` is provided by main.py and writes to the relay WS.
Requires system GStreamer + gst-python (gi). Imported only on the Jetson (main.py
imports it locally), so CI without GStreamer is unaffected.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import gi  # type: ignore

gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")
from gi.repository import Gst, GstSdp, GstWebRTC  # type: ignore  # noqa: E402

from drone.agent.video_pipeline import build_video_pipeline
from drone.common.signaling import SignalKind, SignalMsg

Gst.init(None)

SendSignal = Callable[[SignalMsg], Awaitable[None]]


class WebRTCPublisher:
    def __init__(self, cfg, send_signal: SendSignal) -> None:
        self.cfg = cfg
        self.send_signal = send_signal
        self._peers: dict[str, Gst.Pipeline] = {}

    async def handle_offer(self, sig: SignalMsg) -> None:
        op = sig.operator_id
        desc = build_video_pipeline(
            name="rgb",
            device=self.cfg.webcam_device,
            bitrate_bps=self.cfg.video_bitrate_bps,
            use_test_pattern=self.cfg.video_test_pattern,
        )
        pipe = Gst.parse_launch(desc)
        self._peers[op] = pipe
        webrtc = pipe.get_by_name("rgb")
        webrtc.connect("on-ice-candidate",
                       lambda el, mline, cand: self._on_ice(op, mline, cand))

        _, sdpmsg = GstSdp.SDPMessage.new_from_text(sig.sdp)
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
        promise = Gst.Promise.new()
        webrtc.emit("set-remote-description", offer, promise)
        promise.interrupt()
        pipe.set_state(Gst.State.PLAYING)

        def _on_answer(prom, _):
            reply = prom.get_reply()
            answer = reply.get_value("answer")
            p2 = Gst.Promise.new()
            webrtc.emit("set-local-description", answer, p2)
            p2.interrupt()
            self._post(SignalMsg(kind=SignalKind.ANSWER, operator_id=op,
                                 sdp=answer.sdp.as_text()))

        webrtc.emit("create-answer", None,
                    Gst.Promise.new_with_change_func(_on_answer, None))

    def _on_ice(self, op, mline, candidate):
        self._post(SignalMsg(kind=SignalKind.ICE, operator_id=op,
                             candidate={"candidate": candidate, "sdpMLineIndex": mline}))

    async def handle_ice(self, sig: SignalMsg) -> None:
        pipe = self._peers.get(sig.operator_id)
        if pipe and sig.candidate:
            webrtc = pipe.get_by_name("rgb")
            webrtc.emit("add-ice-candidate",
                        sig.candidate["sdpMLineIndex"], sig.candidate["candidate"])

    async def handle_bye(self, sig: SignalMsg) -> None:
        pipe = self._peers.pop(sig.operator_id, None)
        if pipe:
            pipe.set_state(Gst.State.NULL)

    def _post(self, sig: SignalMsg) -> None:
        import asyncio
        asyncio.create_task(self.send_signal(sig))
