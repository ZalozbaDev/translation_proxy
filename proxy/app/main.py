import logging
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .backends import BackendError, LibreTranslateClient, SotraClient
from .config import Settings, settings
from .routing import Plan, Route, plan_route, supported_languages

log = logging.getLogger("sotra_libretranslate_proxy")
logging.basicConfig(level=logging.INFO)


LANGUAGE_NAMES: dict[str, str] = {
    "hsb": "Upper Sorbian",
    "dsb": "Lower Sorbian",
    "de": "German",
    "en": "English",
    "cs": "Czech",
    "pl": "Polish",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    app.state.http = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    app.state.sotra = SotraClient(settings, app.state.http)
    app.state.libre = LibreTranslateClient(settings, app.state.http)
    log.info(
        "proxy ready: sotra=%s, libretranslate=%s, pivots=%s",
        settings.sotra_url,
        settings.libretranslate_url,
        settings.pivot_languages,
    )
    log.info(
        "matrix: sotra_pairs=%d, libre_langs=%s",
        len(settings.sotra_pairs),
        sorted(settings.libretranslate_langs),
    )
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(
    title="sotra + LibreTranslate proxy",
    version="0.1.0",
    lifespan=lifespan,
)


class TranslateRequest(BaseModel):
    q: str
    source: str
    target: str
    format: str | None = "text"
    api_key: str | None = ""


class TranslateResponse(BaseModel):
    translatedText: str


class DetectResponse(BaseModel):
    confidence: float
    language: str


async def _execute(plan: Plan, text: str, request: Request) -> str:
    sotra: SotraClient = request.app.state.sotra
    libre: LibreTranslateClient = request.app.state.libre
    current = text
    for backend, src, tgt in plan.hops():
        if backend == "sotra":
            current = await sotra.translate(current, src, tgt)
        elif backend == "libretranslate":
            current = await libre.translate(current, src, tgt)
        else:
            raise BackendError(f"unknown backend in plan: {backend}")
    return current


async def _translate_common(
    q: str, source: str, target: str, request: Request
) -> TranslateResponse:
    cfg: Settings = request.app.state.settings
    plan = plan_route(cfg, source, target)
    if plan.route is Route.UNSUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=(
                f"translation {source!r} -> {target!r} is not supported "
                f"by any configured backend or pivot"
            ),
        )
    log.info(
        "translate %s -> %s via %s%s (len=%d)",
        source,
        target,
        plan.route.value,
        f" pivot={plan.pivot}" if plan.pivot else "",
        len(q),
    )
    try:
        translated = await _execute(plan, q, request)
    except BackendError as exc:
        log.warning("backend error on %s -> %s: %s", source, target, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return TranslateResponse(translatedText=translated)


@app.post("/translate", response_model=TranslateResponse)
async def translate(request: Request):
    # LibreTranslate accepts both JSON and form-encoded payloads at /translate.
    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("application/x-www-form-urlencoded") or content_type.startswith(
            "multipart/form-data"
        ):
            form = await request.form()
            payload = TranslateRequest(
                q=str(form.get("q", "")),
                source=str(form.get("source", "")),
                target=str(form.get("target", "")),
                format=str(form.get("format", "text")),
                api_key=str(form.get("api_key", "")),
            )
        else:
            payload = TranslateRequest.model_validate(await request.json())
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid translate request") from exc
    return await _translate_common(payload.q, payload.source, payload.target, request)


@app.post("/translate-form", response_model=TranslateResponse, include_in_schema=False)
async def translate_form(
    request: Request,
    q: Annotated[str, Form()],
    source: Annotated[str, Form()],
    target: Annotated[str, Form()],
    format: Annotated[str | None, Form()] = "text",
    api_key: Annotated[str | None, Form()] = "",
):
    return await _translate_common(q, source, target, request)


@app.get("/languages")
async def languages(request: Request):
    cfg: Settings = request.app.state.settings
    matrix = supported_languages(cfg)
    return [
        {
            "code": code,
            "name": LANGUAGE_NAMES.get(code, code),
            "targets": sorted(targets),
        }
        for code, targets in sorted(matrix.items())
        if targets
    ]


@app.post("/detect")
async def detect() -> list[DetectResponse]:
    # sotra has no detect endpoint and we don't ship one here. jigasi never
    # calls /detect, it always supplies `source`. We return an empty list so
    # polite clients don't crash on an unexpected 404.
    return []


@app.get("/frontend/settings")
async def frontend_settings():
    # Minimal stub so generic libretranslate clients that probe this endpoint
    # don't error out.
    cfg: Settings = app.state.settings
    return {
        "apiKeys": bool(cfg.libretranslate_api_key),
        "charLimit": 0,
        "frontendTimeout": int(cfg.request_timeout_seconds * 1000),
        "keyRequired": False,
        "language": {
            "source": {"code": "auto", "name": "Auto Detect"},
            "target": {"code": "en", "name": "English"},
        },
        "suggestions": False,
        "supportedFilesFormat": [],
    }


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})
