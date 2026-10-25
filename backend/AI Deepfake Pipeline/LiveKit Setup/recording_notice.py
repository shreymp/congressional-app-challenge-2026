"""Play the fixed disclosure before opening any caller audio processing stream."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import struct
import wave

NOTICE_TEXT = "This call is being recorded."
NOTICE_PATH = Path(__file__).with_name("assets") / "recording_notice.wav"
SAMPLE_RATE = 16000
FRAME_SAMPLES = 320
NOTICE_TIMEOUT_SEC = 15
log = logging.getLogger("scam-guard.notice")


def read_notice(path: Path = NOTICE_PATH) -> bytes:
    """Reject missing, empty, silent, truncated or incorrectly encoded assets."""
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
            raise ValueError("Recording notice must be mono 16-bit PCM at 16 kHz")
        count = wav.getnframes()
        if not SAMPLE_RATE // 2 <= count <= SAMPLE_RATE * 10:
            raise ValueError("Recording notice must last between 0.5 and 10 seconds")
        pcm = wav.readframes(count)
    if len(pcm) != count * 2 or not any(abs(v[0]) > 100 for v in struct.iter_unpack("<h", pcm)):
        raise ValueError("Recording notice is silent or truncated")
    return pcm


async def play_recording_notice(room, *, rtc_module=None) -> None:
    """Publish once to the answered call, drain playback, then remove the track.

    The senior's app must have published its microphone before this is called; an
    active SIP caller alone does not prove pickup. Publishing earlier would
    answer the telephone while the senior's app was still ringing. An exception must
    prevent the caller stream, transcription and optional recording from starting.
    rtc_module allows offline transport tests without a LiveKit connection.
    """
    if rtc_module is None:
        from livekit import rtc as rtc_module
    pcm = read_notice()
    source = rtc_module.AudioSource(SAMPLE_RATE, 1, queue_size_ms=200)
    publication = None
    try:
        track = rtc_module.LocalAudioTrack.create_audio_track("recording-notice", source)
        publication = await room.local_participant.publish_track(
            track, rtc_module.TrackPublishOptions(source=rtc_module.TrackSource.SOURCE_MICROPHONE))
        await asyncio.wait_for(publication.wait_for_subscription(), timeout=5)
        # Allow the new receiver path to settle, and preserve the final syllable before
        # unpublishing. These buffers contain silence, never caller audio.
        silence = bytes(SAMPLE_RATE * 2 * 3 // 10)
        audio = silence + pcm + silence
        frame_bytes = FRAME_SAMPLES * 2
        for offset in range(0, len(audio), frame_bytes):
            if not room.isconnected():
                raise RuntimeError("Call ended during the recording notice")
            data = audio[offset:offset + frame_bytes].ljust(frame_bytes, b"\0")
            await source.capture_frame(rtc_module.AudioFrame(
                data=data, sample_rate=SAMPLE_RATE, num_channels=1,
                samples_per_channel=FRAME_SAMPLES))
        await source.wait_for_playout()
        log.info("recording notice playback completed in %s", room.name)
    finally:
        try:
            source.clear_queue()
            if publication is not None and room.isconnected():
                await asyncio.wait_for(room.local_participant.unpublish_track(publication.sid), timeout=2)
        finally:
            await source.aclose()
