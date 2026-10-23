"""Offline disclosure audio/transport tests using the real playback implementation."""
import asyncio
from pathlib import Path
import struct
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

import recording_notice as notice


class NoticeAssetTests(unittest.TestCase):
    def make_wav(self, folder, *, rate=16000, channels=1, width=2, pcm=None):
        path = Path(folder) / "notice.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(pcm if pcm is not None else struct.pack("<h", 1000) * 16000)
        return path

    def test_bundled_spoken_asset_is_nonempty_and_matches_manifest(self):
        import hashlib
        import json
        pcm = notice.read_notice()
        self.assertGreater(len(pcm), notice.SAMPLE_RATE)
        metadata = json.loads(notice.NOTICE_PATH.with_suffix(".json").read_text())
        self.assertEqual(metadata["text"], notice.NOTICE_TEXT)
        self.assertEqual(hashlib.sha256(notice.NOTICE_PATH.read_bytes()).hexdigest(), metadata["sha256"])

    def test_reads_expected_pcm(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(len(notice.read_notice(self.make_wav(folder))), 32000)

    def test_rejects_silence_empty_wrong_format_and_truncated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for options in ({"pcm": b""}, {"pcm": bytes(32000)}, {"rate": 8000},
                            {"channels": 2}, {"width": 1}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    notice.read_notice(self.make_wav(folder, **options))
            path = self.make_wav(folder)
            path.write_bytes(path.read_bytes()[:-100])
            with self.assertRaises(ValueError):
                notice.read_notice(path)

    def test_missing_asset_fails(self):
        with self.assertRaises(FileNotFoundError):
            notice.read_notice(Path("/nonexistent/cac/notice.wav"))


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    def setup_transport(self, *, stalled=False, broken=False):
        events, frames = [], []
        self.subscribing = asyncio.Event()
        owner = self

        class Source:
            def __init__(self, rate, channels, queue_size_ms):
                owner.assertEqual((rate, channels, queue_size_ms), (16000, 1, 200))
            async def capture_frame(self, frame):
                if broken:
                    raise RuntimeError("transport failed")
                events.append("frame")
                frames.append(frame)
            async def wait_for_playout(self): events.append("drained")
            def clear_queue(self): events.append("cleared")
            async def aclose(self): events.append("closed")

        class Publication:
            sid = "notice-track"
            async def wait_for_subscription(self):
                owner.subscribing.set()
                if stalled:
                    await asyncio.Event().wait()
                events.append("subscribed")

        class Room:
            name = "call-test"
            def __init__(self): self.local_participant = self
            def isconnected(self): return True
            async def publish_track(self, track, options):
                events.append("published")
                return Publication()
            async def unpublish_track(self, sid):
                owner.assertEqual(sid, "notice-track")
                events.append("unpublished")

        rtc = types.SimpleNamespace(
            AudioSource=Source,
            LocalAudioTrack=types.SimpleNamespace(create_audio_track=lambda name, source: source),
            TrackPublishOptions=lambda **kwargs: kwargs,
            TrackSource=types.SimpleNamespace(SOURCE_MICROPHONE=1),
            AudioFrame=lambda **kwargs: types.SimpleNamespace(**kwargs))
        return Room(), rtc, events, frames

    async def test_subscribes_before_speech_and_drains_before_cleanup(self):
        room, rtc, events, frames = self.setup_transport()
        pcm = struct.pack("<h", 1000) * 16000
        with patch.object(notice, "read_notice", return_value=pcm):
            await notice.play_recording_notice(room, rtc_module=rtc)
        self.assertLess(events.index("subscribed"), events.index("frame"))
        self.assertEqual(events[-4:], ["drained", "cleared", "unpublished", "closed"])
        self.assertEqual(b"".join(frame.data for frame in frames), bytes(9600) + pcm + bytes(9600))
        self.assertTrue(all(len(frame.data) == 640 and frame.samples_per_channel == 320 for frame in frames))

    async def test_transport_failure_cleans_up_and_propagates(self):
        room, rtc, events, _ = self.setup_transport(broken=True)
        with patch.object(notice, "read_notice", return_value=bytes(32000)):
            with self.assertRaisesRegex(RuntimeError, "transport failed"):
                await notice.play_recording_notice(room, rtc_module=rtc)
        self.assertEqual(events[-3:], ["cleared", "unpublished", "closed"])

    async def test_cancellation_while_waiting_for_receiver_cleans_up(self):
        room, rtc, events, frames = self.setup_transport(stalled=True)
        with patch.object(notice, "read_notice", return_value=bytes(32000)):
            task = asyncio.create_task(notice.play_recording_notice(room, rtc_module=rtc))
            await self.subscribing.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(frames)
        self.assertEqual(events[-3:], ["cleared", "unpublished", "closed"])


if __name__ == "__main__":
    unittest.main()
