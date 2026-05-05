# Package A — sotra + LibreTranslate combination proxy

A standalone container that fronts **sotra** (branch
`workaround_jitsi_limitation`, model `sotra-lsf-ds`) and **LibreTranslate**
(`v1.9.5`) behind a single LibreTranslate-compatible HTTP API. Jigasi's
existing `LibreTranslateTranslationService` speaks to this proxy without any
code changes — just point `org.jitsi.jigasi.transcription.libreTranslate.api_url`
at it.

## Routing

For each `(source, target)` pair the proxy chooses one of five plans:

| Plan                    | When                                                                |
| ----------------------- | ------------------------------------------------------------------- |
| `identity`              | `source == target` (text returned as-is)                            |
| `sotra`                 | pair is in `SOTRA_PAIRS`                                            |
| `libretranslate`        | both langs are in `LIBRETRANSLATE_LANGS` (and not covered by sotra) |
| `chain_sotra_libre`     | `source → pivot` via sotra, `pivot → target` via libretranslate     |
| `chain_libre_sotra`     | `source → pivot` via libretranslate, `pivot → target` via sotra     |
| *400 Bad Request*       | no plan reaches the target                                          |

Sotra is preferred for any pair it can handle directly. Chains use
`PIVOT_LANGUAGES` in order (default: `de,en`).

### Scenarios covered (task spec §(1)(a))

| Scenario                                    | Example         | Plan                  |
| ------------------------------------------- | --------------- | --------------------- |
| i. fully via sotra                          | `hsb → de`      | `sotra`               |
| ii. partial sotra / partial libretranslate  | `cs → hsb`      | `sotra` (preferred)   |
| ii. partial sotra / partial libretranslate  | `cs → de`       | `libretranslate`      |
| iii. libretranslate only                    | `de → en`       | `libretranslate`      |
| iv. chained                                 | `hsb → en`      | `chain_sotra_libre` (pivot `de`) |
| iv. chained                                 | `en → dsb`      | `chain_libre_sotra` (pivot `de`) |

## Endpoints

All paths match the LibreTranslate v1 contract that jigasi already speaks.

- `POST /translate` — body `{"q","source","target","format"?,"api_key"?}` → `{"translatedText"}`
- `POST /translate-form` — same, form-encoded (for curl parity with upstream LibreTranslate)
- `GET  /languages` — list of `{code,name,targets[]}` computed from the live routing matrix
- `POST /detect` — returns `[]` (sotra has no detect; jigasi never calls this)
- `GET  /frontend/settings` — minimal stub for generic LibreTranslate frontends
- `GET  /health` — liveness

## Configuration

All settings read from env vars at container start.

| Var                      | Default                           | Purpose                                                  |
| ------------------------ | --------------------------------- | -------------------------------------------------------- |
| `SOTRA_URL`              | `http://sotra:3000`               | Upstream sotra base URL                                  |
| `LIBRETRANSLATE_URL`     | `http://libretranslate:5000`      | Upstream LibreTranslate base URL                         |
| `LIBRETRANSLATE_API_KEY` | *(empty)*                         | Forwarded as `api_key` to LibreTranslate                 |
| `PIVOT_LANGUAGES`        | `de,en`                           | Ordered list of pivots for chained routes                |
| `REQUEST_TIMEOUT`        | `30`                              | Per-hop HTTP timeout, seconds                            |
| `SOTRA_PAIRS`            | `hsb->de,de->hsb,dsb->de,de->dsb,hsb->dsb,dsb->hsb,cs->hsb` | Directional pairs sotra handles |
| `LIBRETRANSLATE_LANGS`   | `en,de,cs,pl`                     | Full mesh assumed across this set                        |

## Running

```sh
# 1. Clone sotra alongside this repo
git clone -b workaround_jitsi_limitation \
  https://github.com/ZalozbaDev/sotra_modele ../sotra_modele

# 2. Start everything
docker compose up --build

# 3. Try it (jigasi-equivalent request)
curl -s -X POST http://localhost:5050/translate \
  -H 'Content-Type: application/json' \
  -d '{"q":"To je test.","source":"hsb","target":"en"}'
# {"translatedText":"This is a test."}
```

Point jigasi at `http://<proxy-host>:5050/translate` and nothing else changes
in jigasi itself.

## Tests

Three layers, all driven from `proxy/`:

| Layer            | Marker        | Stack required? | Speed | What it covers                                                |
| ---------------- | ------------- | --------------- | ----- | ------------------------------------------------------------- |
| Unit             | *(default)*   | no              | <1 s  | Routing decision for every task scenario, API shape with mocked backends |
| Live integration | `-m live`     | yes             | ~5 s  | Real sotra + LibreTranslate behind the proxy, all 4 task scenarios |
| Audio            | `-m audio`    | yes + fixtures  | varies | WAV/MP3 → faster-whisper STT → proxy → assertion              |

Quick start:

```sh
cd package-a-sotra-libretranslate/proxy
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt

pytest               # unit
pytest -m live       # live (stack must be up)
AUDIO_FIXTURES_DIR=… pytest -m audio   # audio
```

Captured handover results are in [`TEST_RESULTS.md`](TEST_RESULTS.md).
Audio harness deep-dive:
[`proxy/tests/audio_harness/README.md`](proxy/tests/audio_harness/README.md).

## Layout

```
package-a-sotra-libretranslate/
├── docker-compose.yml           # libretranslate + sotra + proxy
├── README.md
└── proxy/
    ├── Dockerfile
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── pytest.ini
    ├── app/
    │   ├── config.py            # env-driven matrices + Settings
    │   ├── routing.py           # Plan / plan_route / supported_languages
    │   ├── backends.py          # SotraClient, LibreTranslateClient
    │   └── main.py              # FastAPI app (libretranslate-compatible API)
    └── tests/
        ├── test_routing.py      # unit — one test per task scenario
        ├── test_api.py          # API — mocked backends via respx
        ├── test_live.py         # live — hits the running stack
        └── audio_harness/       # WAV/MP3 → STT → proxy harness
            ├── harness.py
            ├── test_audio.py
            ├── show_results.py  # pretty-print transcripts + translations
            ├── example_manifest.json
            └── README.md
```
