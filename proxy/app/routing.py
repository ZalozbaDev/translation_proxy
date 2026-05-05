from dataclasses import dataclass
from enum import Enum

from .config import Settings


class Route(Enum):
    IDENTITY = "identity"
    SOTRA = "sotra"
    LIBRETRANSLATE = "libretranslate"
    CHAIN_SOTRA_LIBRE = "chain_sotra_libre"
    CHAIN_LIBRE_SOTRA = "chain_libre_sotra"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Plan:
    route: Route
    source: str
    target: str
    pivot: str | None = None

    def hops(self) -> list[tuple[str, str, str]]:
        """Return the concrete [(backend, src, tgt), ...] hops to execute."""
        if self.route is Route.IDENTITY:
            return []
        if self.route is Route.SOTRA:
            return [("sotra", self.source, self.target)]
        if self.route is Route.LIBRETRANSLATE:
            return [("libretranslate", self.source, self.target)]
        assert self.pivot is not None
        if self.route is Route.CHAIN_SOTRA_LIBRE:
            return [
                ("sotra", self.source, self.pivot),
                ("libretranslate", self.pivot, self.target),
            ]
        if self.route is Route.CHAIN_LIBRE_SOTRA:
            return [
                ("libretranslate", self.source, self.pivot),
                ("sotra", self.pivot, self.target),
            ]
        return []


def _sotra_supports(settings: Settings, src: str, tgt: str) -> bool:
    return (src, tgt) in settings.sotra_pairs


def _libre_supports(settings: Settings, src: str, tgt: str) -> bool:
    if src == tgt:
        return False
    return src in settings.libretranslate_langs and tgt in settings.libretranslate_langs


def plan_route(settings: Settings, source: str, target: str) -> Plan:
    """Decide how to translate (source -> target).

    Preference order: identity, sotra direct, libretranslate direct, chain
    (sotra -> libre, then libre -> sotra) using configured pivot languages.
    """
    if source == target:
        return Plan(Route.IDENTITY, source, target)

    if _sotra_supports(settings, source, target):
        return Plan(Route.SOTRA, source, target)

    if _libre_supports(settings, source, target):
        return Plan(Route.LIBRETRANSLATE, source, target)

    for pivot in settings.pivot_languages:
        if pivot in (source, target):
            continue
        if _sotra_supports(settings, source, pivot) and _libre_supports(
            settings, pivot, target
        ):
            return Plan(Route.CHAIN_SOTRA_LIBRE, source, target, pivot)
        if _libre_supports(settings, source, pivot) and _sotra_supports(
            settings, pivot, target
        ):
            return Plan(Route.CHAIN_LIBRE_SOTRA, source, target, pivot)

    return Plan(Route.UNSUPPORTED, source, target)


def supported_languages(settings: Settings) -> dict[str, set[str]]:
    """Compute the effective src -> {targets} matrix this proxy can serve.

    A pair is reachable if plan_route returns anything other than UNSUPPORTED.
    """
    langs = settings.all_languages
    matrix: dict[str, set[str]] = {}
    for src in langs:
        targets: set[str] = set()
        for tgt in langs:
            if src == tgt:
                continue
            if plan_route(settings, src, tgt).route is not Route.UNSUPPORTED:
                targets.add(tgt)
        matrix[src] = targets
    return matrix
