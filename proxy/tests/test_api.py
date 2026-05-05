import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


@pytest.fixture
def client():
    # Override settings for a deterministic matrix during tests.
    app.dependency_overrides = {}
    with TestClient(app) as c:
        c.app.state.settings = Settings(
            sotra_url="http://sotra-test:3000",
            libretranslate_url="http://libre-test:5000",
            libretranslate_api_key="",
            pivot_languages=("de", "en"),
            sotra_pairs={
                ("hsb", "de"), ("de", "hsb"),
                ("dsb", "de"), ("de", "dsb"),
                ("hsb", "dsb"), ("dsb", "hsb"),
                ("cs", "hsb"),
            },
            libretranslate_langs={"en", "de", "cs", "pl"},
        )
        # rebuild backend clients pointing at the overridden URLs
        from app.backends import LibreTranslateClient, SotraClient
        c.app.state.sotra = SotraClient(c.app.state.settings, c.app.state.http)
        c.app.state.libre = LibreTranslateClient(c.app.state.settings, c.app.state.http)
        yield c


@respx.mock
def test_scenario_i_sotra_only(client):
    respx.post("http://sotra-test:3000/libretranslate").mock(
        return_value=httpx.Response(200, json={"translatedText": "Das ist ein Test."})
    )
    r = client.post(
        "/translate",
        json={"q": "To je test.", "source": "hsb", "target": "de"},
    )
    assert r.status_code == 200
    assert r.json() == {"translatedText": "Das ist ein Test."}
    assert respx.calls.call_count == 1


@respx.mock
def test_translate_accepts_libretranslate_form_payload(client):
    respx.post("http://libre-test:5000/translate").mock(
        return_value=httpx.Response(200, json={"translatedText": "This is a test."})
    )
    r = client.post(
        "/translate",
        data={
            "q": "Das ist ein Test.",
            "source": "de",
            "target": "en",
            "format": "text",
            "api_key": "",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"translatedText": "This is a test."}


@respx.mock
def test_scenario_ii_libretranslate_only(client):
    respx.post("http://libre-test:5000/translate").mock(
        return_value=httpx.Response(200, json={"translatedText": "To je test."})
    )
    r = client.post(
        "/translate",
        json={"q": "Das ist ein Test.", "source": "de", "target": "cs"},
    )
    assert r.status_code == 200
    assert r.json() == {"translatedText": "To je test."}


@respx.mock
def test_scenario_iii_pure_libretranslate_de_en(client):
    respx.post("http://libre-test:5000/translate").mock(
        return_value=httpx.Response(200, json={"translatedText": "This is a test."})
    )
    r = client.post(
        "/translate",
        json={"q": "Das ist ein Test.", "source": "de", "target": "en"},
    )
    assert r.status_code == 200
    assert r.json() == {"translatedText": "This is a test."}


@respx.mock
def test_scenario_iv_chain_hsb_to_en(client):
    respx.post("http://sotra-test:3000/libretranslate").mock(
        return_value=httpx.Response(200, json={"translatedText": "Das ist ein Test."})
    )
    respx.post("http://libre-test:5000/translate").mock(
        return_value=httpx.Response(200, json={"translatedText": "This is a test."})
    )
    r = client.post(
        "/translate",
        json={"q": "To je test.", "source": "hsb", "target": "en"},
    )
    assert r.status_code == 200
    assert r.json() == {"translatedText": "This is a test."}
    # Exactly one call to each backend
    sotra_calls = [c for c in respx.calls if "sotra-test" in str(c.request.url)]
    libre_calls = [c for c in respx.calls if "libre-test" in str(c.request.url)]
    assert len(sotra_calls) == 1
    assert len(libre_calls) == 1


@respx.mock
def test_scenario_iv_reverse_chain_en_to_hsb(client):
    respx.post("http://libre-test:5000/translate").mock(
        return_value=httpx.Response(200, json={"translatedText": "Das ist ein Test."})
    )
    respx.post("http://sotra-test:3000/libretranslate").mock(
        return_value=httpx.Response(200, json={"translatedText": "To je test."})
    )
    r = client.post(
        "/translate",
        json={"q": "This is a test.", "source": "en", "target": "hsb"},
    )
    assert r.status_code == 200
    assert r.json() == {"translatedText": "To je test."}


@respx.mock
def test_backend_error_returns_502(client):
    respx.post("http://sotra-test:3000/libretranslate").mock(
        return_value=httpx.Response(503, text="sotra down")
    )
    r = client.post(
        "/translate",
        json={"q": "To je test.", "source": "hsb", "target": "de"},
    )
    assert r.status_code == 502


def test_unsupported_pair_returns_400(client):
    r = client.post(
        "/translate",
        json={"q": "...", "source": "hsb", "target": "ja"},
    )
    assert r.status_code == 400


def test_languages_endpoint_lists_reachable_targets(client):
    r = client.get("/languages")
    assert r.status_code == 200
    data = {entry["code"]: set(entry["targets"]) for entry in r.json()}
    assert "en" in data.get("hsb", set())  # chained
    assert "de" in data.get("hsb", set())  # direct
    assert "en" in data.get("de", set())   # libretranslate
    assert "hsb" in data.get("en", set())  # reverse chain


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
