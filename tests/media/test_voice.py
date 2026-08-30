from hashlib import sha256

import pytest

from app.media.voice import (
    InvalidVoice,
    resolve_private_voice_path,
    save_voice,
    validate_voice,
)

VOICE_CASES = [
    (b"ID3\x04\x00\x00\x00\x00\x00\x00payload", "voice.mp3", "audio/mpeg", ".mp3"),
    (b"OggS" + b"\x00" * 32, "voice.ogg", "audio/ogg", ".ogg"),
    (b"RIFF" + b"\x00" * 4 + b"WAVEfmt ", "voice.wav", "audio/wav", ".wav"),
    (b"\x1aE\xdf\xa3" + b"\x00" * 32, "voice.webm", "audio/webm", ".webm"),
    (b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 24, "voice.m4a", "audio/mp4", ".m4a"),
]


@pytest.mark.parametrize("data,filename,mime,suffix", VOICE_CASES)
def test_supported_voice_is_saved_without_byte_changes(
    tmp_path, data, filename, mime, suffix
):
    voice = validate_voice(data, filename, mime, duration_ms=1500)
    path = save_voice(tmp_path, 7, voice)

    assert path.suffix == suffix
    assert path.read_bytes() == data
    assert voice.sha256 == sha256(data).hexdigest()
    assert filename not in path.name


def test_browser_recording_mime_with_opus_codec_is_accepted():
    data = b"\x1aE\xdf\xa3" + b"\x00" * 32

    voice = validate_voice(
        data,
        "recording.webm",
        "audio/webm;codecs=opus",
        duration_ms=1500,
    )

    assert voice.mime_type == "audio/webm"
    assert voice.suffix == ".webm"


@pytest.mark.parametrize(
    "data,filename,mime",
    [
        (b"OggS" + b"\x00" * 32, "voice.mp3", "audio/mpeg"),
        (b"ID3" + b"\x00" * 32, "voice.ogg", "audio/ogg"),
        (b"RIFF" + b"\x00" * 32, "voice.wav", "audio/wav"),
    ],
)
def test_mismatched_or_incomplete_voice_signature_is_rejected(data, filename, mime):
    with pytest.raises(InvalidVoice):
        validate_voice(data, filename, mime, duration_ms=1000)


def test_empty_and_unsupported_voice_are_rejected():
    with pytest.raises(InvalidVoice):
        validate_voice(b"", "voice.mp3", "audio/mpeg", duration_ms=1000)
    with pytest.raises(InvalidVoice):
        validate_voice(b"text", "voice.txt", "text/plain", duration_ms=1000)


def test_oversized_voice_is_rejected(monkeypatch):
    monkeypatch.setattr("app.media.voice.MAX_VOICE_BYTES", 8)

    with pytest.raises(InvalidVoice, match="حجم"):
        validate_voice(
            b"ID3" + b"\x00" * 20,
            "voice.mp3",
            "audio/mpeg",
            duration_ms=1000,
        )


def test_recording_longer_than_ten_minutes_is_rejected():
    with pytest.raises(InvalidVoice, match="مدت"):
        validate_voice(
            b"ID3" + b"\x00" * 20,
            "voice.mp3",
            "audio/mpeg",
            duration_ms=600_001,
        )


def test_private_voice_path_cannot_escape_upload_root(tmp_path):
    with pytest.raises(InvalidVoice, match="مسیر"):
        resolve_private_voice_path(tmp_path, "private/voices/1/../../secret.webm")
    with pytest.raises(InvalidVoice, match="مسیر"):
        resolve_private_voice_path(tmp_path, "C:\\secret.webm")
