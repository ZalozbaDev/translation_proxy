"""Audio → translation test cases driven by a fixture manifest."""
from __future__ import annotations

import os

import pytest

from .harness import (
    SOURCE_MATCH_THRESHOLD,
    TARGET_MATCH_THRESHOLD,
    AudioFixture,
    STTUnsupported,
    discover_fixtures,
    similarity,
    supported_whisper_languages,
    transcribe,
    translate_via_proxy,
)


_FIXTURES = discover_fixtures() if os.environ.get("AUDIO_FIXTURES_DIR") else []

pytestmark = [
    pytest.mark.audio,
    pytest.mark.skipif(
        not _FIXTURES,
        reason=(
            "no audio fixtures discovered; set AUDIO_FIXTURES_DIR to a "
            "directory containing manifest.json + .wav files"
        ),
    ),
]


@pytest.mark.parametrize(
    "fixture", _FIXTURES or [None], ids=lambda f: f.label if f else "none"
)
def test_audio_to_translation(fixture: AudioFixture, capsys):
    """End-to-end: STT (if supported) then translate, compare to expected.

    If the source language isn't in the public Whisper tokenizer (e.g. hsb,
    dsb), STT is skipped — the test then validates the translation step
    using the known `expected_source` text. The fixture is marked xfail-ish
    via a printed note rather than a test skip, because translation is
    still being exercised and the user wants to see results."""
    try:
        transcript = transcribe(fixture.wav_path, fixture.source_lang)
        stt_ran = True
    except STTUnsupported as exc:
        if not fixture.expected_source:
            pytest.skip(
                f"STT unsupported for {fixture.source_lang!r} and no "
                f"expected_source provided to fall back on: {exc}"
            )
        transcript = fixture.expected_source
        stt_ran = False
        print(
            f"[harness] STT skipped for {fixture.source_lang!r} "
            f"(unsupported by {os.environ.get('WHISPER_MODEL', 'small')}); "
            f"using expected_source as transcript"
        )

    if stt_ran and fixture.expected_source:
        score = similarity(transcript, fixture.expected_source)
        assert score >= SOURCE_MATCH_THRESHOLD, (
            f"STT drift too large for {fixture.label}: "
            f"score={score:.2f} < {SOURCE_MATCH_THRESHOLD:.2f}\n"
            f"  expected: {fixture.expected_source!r}\n"
            f"  got:      {transcript!r}"
        )

    translated = translate_via_proxy(
        transcript, fixture.source_lang, fixture.target_lang
    )
    assert translated.strip(), \
        f"empty translation for {fixture.label}: input={transcript!r}"

    if fixture.expected_target:
        score = similarity(translated, fixture.expected_target)
        assert score >= TARGET_MATCH_THRESHOLD, (
            f"translation drift too large for {fixture.label}: "
            f"score={score:.2f} < {TARGET_MATCH_THRESHOLD:.2f}\n"
            f"  expected: {fixture.expected_target!r}\n"
            f"  got:      {translated!r}"
        )
