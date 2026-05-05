"""Audio → translation test harness.

Pipeline:
  WAV file
    │
    ▼
  faster-whisper STT  (configurable model size)
    │   produces transcript
    ▼
  Translation (proxy /translate, libretranslate-shaped API)
    │   produces translated text
    ▼
  Compare against expected transcript and expected translation

Fixture layout (point AUDIO_FIXTURES_DIR at this dir):

    audio_fixtures/
        manifest.json
        my_clip.wav
        another.wav
        ...

manifest.json is a list:

    [
      {
        "wav": "my_clip.wav",
        "source_lang": "hsb",
        "target_lang": "en",
        "expected_source": "To je test.",
        "expected_target": "This is a test."
      }
    ]

Either expected_* may be omitted; missing fields skip that comparison.

Run:
  AUDIO_FIXTURES_DIR=/path/to/fixtures \
  pytest -m audio tests/audio_harness/test_audio.py -v
"""
from __future__ import annotations

import difflib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
PROXY_URL = os.environ.get("PROXY_URL", "http://localhost:5050").rstrip("/")
SOURCE_MATCH_THRESHOLD = float(os.environ.get("SOURCE_MATCH_THRESHOLD", "0.55"))
TARGET_MATCH_THRESHOLD = float(os.environ.get("TARGET_MATCH_THRESHOLD", "0.30"))


@dataclass
class AudioFixture:
    wav_path: Path
    source_lang: str
    target_lang: str
    expected_source: str | None
    expected_target: str | None
    note: str | None = None

    @classmethod
    def from_manifest_entry(cls, entry: dict, base: Path) -> "AudioFixture":
        wav = Path(entry["wav"]).expanduser()
        if not wav.is_absolute():
            wav = base / wav
        return cls(
            wav_path=wav,
            source_lang=entry["source_lang"],
            target_lang=entry["target_lang"],
            expected_source=entry.get("expected_source"),
            expected_target=entry.get("expected_target"),
            note=entry.get("note"),
        )

    @property
    def label(self) -> str:
        return (
            f"{self.wav_path.name}({self.source_lang}->{self.target_lang})"
        )


def discover_fixtures() -> list[AudioFixture]:
    fixtures_dir_env = os.environ.get("AUDIO_FIXTURES_DIR")
    if not fixtures_dir_env:
        return []
    base = Path(fixtures_dir_env).expanduser().resolve()
    manifest = base / "manifest.json"
    if not manifest.is_file():
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [AudioFixture.from_manifest_entry(e, base) for e in data]


@lru_cache(maxsize=1)
def get_whisper_model():
    # Imported lazily so the module can be collected when faster-whisper
    # isn't installed (pure unit-test runs).
    from faster_whisper import WhisperModel

    return WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")


@lru_cache(maxsize=1)
def supported_whisper_languages() -> frozenset[str]:
    # The public Whisper checkpoint OpenAI ships (and all faster-whisper
    # default models) does not include Upper or Lower Sorbian. When source
    # audio is in an unsupported language, callers should use the known
    # transcript directly and only validate the translation step.
    from faster_whisper.tokenizer import _LANGUAGE_CODES

    return frozenset(_LANGUAGE_CODES)


class STTUnsupported(RuntimeError):
    """faster-whisper has no tokenizer for the requested language."""


def transcribe(audio_path: Path, language: str) -> str:
    if language not in supported_whisper_languages():
        raise STTUnsupported(
            f"language {language!r} not in faster-whisper "
            f"({WHISPER_MODEL_SIZE}); supply a model trained for it"
        )
    model = get_whisper_model()
    segments, _info = model.transcribe(str(audio_path), language=language)
    return " ".join(s.text.strip() for s in segments).strip()


def translate_via_proxy(text: str, source: str, target: str) -> str:
    import httpx

    response = httpx.post(
        f"{PROXY_URL}/translate",
        json={"q": text, "source": source, "target": target, "format": "text"},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["translatedText"]


def similarity(a: str, b: str) -> float:
    """Char-level similarity ratio in [0, 1]. Robust to small drift in
    NMT/STT output (we compare normalized lowercase, whitespace-collapsed)."""
    a_norm = " ".join(a.lower().split())
    b_norm = " ".join(b.lower().split())
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
