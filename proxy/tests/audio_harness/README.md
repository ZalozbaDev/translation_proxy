# Audio → translation test harness

End-to-end pipeline:

```
WAV file ─► faster-whisper STT ─► proxy /translate ─► assertion
```

The harness compares both the STT transcript (against `expected_source`)
and the translation (against `expected_target`) using a character-level
similarity ratio so it tolerates small NMT/STT drift.

## Providing fixtures

Set `AUDIO_FIXTURES_DIR` to a directory containing:

- `manifest.json` — list of fixture entries (see `example_manifest.json`)
- one `.wav` file per entry, referenced by the manifest's `wav` field

Manifest entry schema:

| Field             | Required | Notes                                                     |
| ----------------- | -------- | --------------------------------------------------------- |
| `wav`             | yes      | Filename relative to the fixtures dir                     |
| `source_lang`     | yes      | BCP-47 code (`hsb`, `dsb`, `de`, `en`, `cs`, `pl`)        |
| `target_lang`     | yes      | BCP-47 code                                               |
| `expected_source` | no       | If set, asserted against STT output (similarity ratio)    |
| `expected_target` | no       | If set, asserted against translation output               |
| `note`            | no       | Free-form, shown on failure                               |

## Running

```sh
# 1. Start the stack
cd ../../..
docker compose up -d --wait

# 2. Set fixtures dir, install deps, run
export AUDIO_FIXTURES_DIR=/path/to/fixtures
pip install -r ../requirements-dev.txt
pytest -m audio tests/audio_harness/test_audio.py -v
```

## Tunables (env vars)

- `WHISPER_MODEL`           — `tiny`, `base`, `small`, `medium`, `large-v3` (default `small`)
- `PROXY_URL`               — proxy base URL (default `http://localhost:5050`)
- `SOURCE_MATCH_THRESHOLD`  — STT similarity threshold (default `0.55`)
- `TARGET_MATCH_THRESHOLD`  — translation similarity threshold (default `0.30`)

`SOURCE_MATCH_THRESHOLD` is generous because the public Whisper model has
limited Sorbian quality. If you have a higher-quality Whisper model
(your trained `whisper_large_v3_turbo_hsb`), point `WHISPER_MODEL` at a
local checkpoint dir and tighten the threshold.

`TARGET_MATCH_THRESHOLD` is intentionally low since identical-meaning
NMT translations can differ in surface form (`"Welcome to us"` vs
`"Welcome to our place"`); tighten it for tests that should match
exactly.
