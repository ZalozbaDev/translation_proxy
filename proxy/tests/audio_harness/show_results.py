"""Run the harness across the manifest and print a results table."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.audio_harness.harness import (  # noqa: E402
    STTUnsupported,
    discover_fixtures,
    similarity,
    transcribe,
    translate_via_proxy,
)


def main() -> int:
    if not os.environ.get("AUDIO_FIXTURES_DIR"):
        print("set AUDIO_FIXTURES_DIR to the manifest directory")
        return 2

    fixtures = discover_fixtures()
    if not fixtures:
        print("no fixtures found")
        return 1

    rows: list[tuple[str, str, str, str, str, str]] = []
    for fx in fixtures:
        try:
            transcript = transcribe(fx.wav_path, fx.source_lang)
            stt_note = "stt"
        except STTUnsupported:
            transcript = fx.expected_source or ""
            stt_note = "stt-skip"
        translated = translate_via_proxy(
            transcript, fx.source_lang, fx.target_lang
        )
        src_score = (
            f"{similarity(transcript, fx.expected_source):.2f}"
            if fx.expected_source and stt_note == "stt"
            else "—"
        )
        tgt_score = (
            f"{similarity(translated, fx.expected_target):.2f}"
            if fx.expected_target
            else "—"
        )
        rows.append(
            (
                f"{fx.source_lang}->{fx.target_lang}",
                stt_note,
                transcript,
                translated,
                src_score,
                tgt_score,
            )
        )

    # pretty print
    widths = [max(len(str(r[i])) for r in rows) for i in range(6)]
    headers = ("dir", "mode", "transcript", "translation", "stt~", "trans~")
    widths = [max(w, len(h)) for w, h in zip(widths, headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for r in rows:
        print(fmt.format(*r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
