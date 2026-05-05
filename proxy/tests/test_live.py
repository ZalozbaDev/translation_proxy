"""Live integration tests against the docker-compose stack.

These hit the running proxy at PROXY_URL (default http://localhost:5050).
They are skipped automatically if the proxy isn't reachable, so the suite
stays green in environments without docker (CI, dev laptop with stack down).

Run all live tests:
    docker compose up -d --wait
    pytest -m live tests/test_live.py -v

Skip live tests in normal pytest runs (default behaviour — no -m live)."""
from __future__ import annotations

import os

import httpx
import pytest

PROXY_URL = os.environ.get("PROXY_URL", "http://localhost:5050").rstrip("/")
DEFAULT_TIMEOUT = httpx.Timeout(60.0)


def _proxy_reachable() -> bool:
    try:
        r = httpx.get(f"{PROXY_URL}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not _proxy_reachable(),
        reason=f"proxy not reachable at {PROXY_URL}",
    ),
]


def _translate(q: str, source: str, target: str) -> str:
    r = httpx.post(
        f"{PROXY_URL}/translate",
        json={"q": q, "source": source, "target": target, "format": "text"},
        timeout=DEFAULT_TIMEOUT,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    body = r.json()
    text = body["translatedText"]
    assert isinstance(text, str) and text.strip(), f"empty translation: {body!r}"
    return text


# Fixtures — short, well-known phrases. We don't pin exact translations
# (NMT output drifts between model versions) — we assert the call succeeds
# and produces a non-empty target-language string.

class TestScenarioI_FullySotra:
    """Pairs handled entirely by sotra."""

    def test_hsb_to_de(self):
        out = _translate("To je test.", "hsb", "de")
        assert out  # something german-ish

    def test_de_to_hsb(self):
        out = _translate("Das ist ein Test.", "de", "hsb")
        assert out

    def test_dsb_to_hsb(self):
        out = _translate("To jo test.", "dsb", "hsb")
        assert out

    def test_hsb_to_dsb(self):
        out = _translate("To je test.", "hsb", "dsb")
        assert out


class TestScenarioII_PartialSotraPartialLibre:
    """Pairs the task specifically calls out for the mixed scenario."""

    def test_cs_to_hsb_via_sotra(self):
        out = _translate("To je test.", "cs", "hsb")
        assert out

    def test_cs_to_de_via_libretranslate(self):
        out = _translate("To je test.", "cs", "de")
        assert out


class TestScenarioIII_LibreTranslateOnly:
    def test_de_to_en(self):
        out = _translate("Das ist ein Test.", "de", "en")
        # libretranslate models tend to produce "this is a test." or similar
        assert out
        assert "test" in out.lower() or "test" in out

    def test_en_to_de(self):
        out = _translate("This is a test.", "en", "de")
        assert out

    def test_pl_to_en(self):
        out = _translate("To jest test.", "pl", "en")
        assert out


class TestScenarioIV_Chained:
    """Two-hop routes through the de pivot."""

    def test_hsb_to_en_chains_via_de(self):
        out = _translate("To je test.", "hsb", "en")
        assert out

    def test_dsb_to_en_chains_via_de(self):
        out = _translate("To jo test.", "dsb", "en")
        assert out

    def test_en_to_hsb_chains_via_de(self):
        out = _translate("This is a test.", "en", "hsb")
        assert out

    def test_pl_to_dsb_chains_via_de(self):
        out = _translate("To jest test.", "pl", "dsb")
        assert out


class TestUnsupported:
    def test_japanese_target_returns_400(self):
        r = httpx.post(
            f"{PROXY_URL}/translate",
            json={"q": "Hello", "source": "en", "target": "ja", "format": "text"},
            timeout=DEFAULT_TIMEOUT,
        )
        assert r.status_code == 400


class TestLanguagesEndpoint:
    def test_lists_required_pairs(self):
        r = httpx.get(f"{PROXY_URL}/languages", timeout=DEFAULT_TIMEOUT)
        assert r.status_code == 200
        matrix = {entry["code"]: set(entry["targets"]) for entry in r.json()}
        # Required by the task spec
        for src, tgt in [
            ("hsb", "de"), ("de", "hsb"),
            ("dsb", "hsb"), ("hsb", "dsb"),
            ("cs", "hsb"),
            ("de", "en"), ("en", "de"),
            ("hsb", "en"), ("dsb", "en"),
            ("en", "hsb"), ("en", "dsb"),
        ]:
            assert tgt in matrix.get(src, set()), \
                f"matrix missing required pair {src}->{tgt}"
