from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from uuid import uuid4

MAX_VOICE_BYTES = 25 * 1024 * 1024
MAX_RECORDING_MS = 600_000

MIME_SUFFIXES = {
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
}


class InvalidVoice(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedVoice:
    data: bytes
    mime_type: str
    suffix: str
    sha256: str
    duration_ms: int | None


def _signature_matches(data: bytes, suffix: str) -> bool:
    if suffix == ".mp3":
        return data.startswith(b"ID3") or (
            len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
        )
    if suffix == ".ogg":
        return data.startswith(b"OggS")
    if suffix == ".wav":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    if suffix == ".webm":
        return data.startswith(b"\x1aE\xdf\xa3")
    if suffix == ".m4a":
        return len(data) >= 12 and data[4:8] == b"ftyp"
    return False


def validate_voice(
    data: bytes,
    filename: str,
    content_type: str,
    *,
    duration_ms: int | None,
) -> ValidatedVoice:
    if not data:
        raise InvalidVoice("فایل Voice خالی است")
    if len(data) > MAX_VOICE_BYTES:
        raise InvalidVoice("حجم Voice بیشتر از حد مجاز است")
    mime_type = content_type.lower().strip()
    expected_suffix = MIME_SUFFIXES.get(mime_type)
    if expected_suffix is None:
        raise InvalidVoice("نوع Voice پشتیبانی نمی‌شود")
    supplied_suffix = Path(filename).suffix.lower()
    if supplied_suffix != expected_suffix:
        raise InvalidVoice("پسوند Voice با نوع اعلام‌شده هم‌خوان نیست")
    if not _signature_matches(data, expected_suffix):
        raise InvalidVoice("ساختار Voice با نوع اعلام‌شده هم‌خوان نیست")
    if duration_ms is not None and not 0 < duration_ms <= MAX_RECORDING_MS:
        raise InvalidVoice("مدت Voice بیشتر از حد مجاز است")
    return ValidatedVoice(
        data=data,
        mime_type=mime_type,
        suffix=expected_suffix,
        sha256=sha256(data).hexdigest(),
        duration_ms=duration_ms,
    )


def save_voice(root: Path, draft_id: int, voice: ValidatedVoice) -> Path:
    directory = root / "private" / "voices" / str(draft_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}{voice.suffix}"
    try:
        path.write_bytes(voice.data)
        if sha256(path.read_bytes()).hexdigest() != voice.sha256:
            raise OSError("stored voice checksum mismatch")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def resolve_private_voice_path(root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path.replace("\\", "/"))
    if (
        not relative_path
        or candidate.is_absolute()
        or PureWindowsPath(relative_path).is_absolute()
        or ".." in candidate.parts
        or candidate.parts[:2] != ("private", "voices")
    ):
        raise InvalidVoice("مسیر Voice معتبر نیست")
    private_root = (root / "private" / "voices").resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(private_root):
        raise InvalidVoice("مسیر Voice معتبر نیست")
    return resolved

