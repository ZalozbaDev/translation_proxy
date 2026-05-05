import json
import os
from dataclasses import dataclass, field


def _parse_pairs(raw: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "->" in token:
            src, tgt = token.split("->", 1)
        elif ":" in token:
            src, tgt = token.split(":", 1)
        else:
            raise ValueError(f"invalid pair spec: {token!r} (use 'src->tgt')")
        pairs.add((src.strip(), tgt.strip()))
    return pairs


# sotra (workaround_jitsi_limitation branch, sotra-lsf-ds model).
# The model card advertises hsb/dsb/de and limited cs. Override via
# SOTRA_PAIRS if the deployed model differs.
DEFAULT_SOTRA_PAIRS: set[tuple[str, str]] = {
    ("hsb", "de"),
    ("de", "hsb"),
    ("dsb", "de"),
    ("de", "dsb"),
    ("hsb", "dsb"),
    ("dsb", "hsb"),
    ("cs", "hsb"),
}

# LibreTranslate v1.9.5 with the default Argos model pack. These are the
# languages we care about for this proxy (the task spec calls out hsb,
# dsb, de, cs, pl, en). LibreTranslate is treated as a full mesh over
# its supported set.
DEFAULT_LIBRETRANSLATE_LANGS: set[str] = {"en", "de", "cs", "pl"}


@dataclass
class Settings:
    sotra_url: str = os.environ.get("SOTRA_URL", "http://sotra:3000")
    libretranslate_url: str = os.environ.get(
        "LIBRETRANSLATE_URL", "http://libretranslate:5000"
    )
    libretranslate_api_key: str = os.environ.get("LIBRETRANSLATE_API_KEY", "")
    pivot_languages: tuple[str, ...] = tuple(
        os.environ.get("PIVOT_LANGUAGES", "de,en").split(",")
    )
    request_timeout_seconds: float = float(os.environ.get("REQUEST_TIMEOUT", "30"))
    sotra_pairs: set[tuple[str, str]] = field(
        default_factory=lambda: _parse_pairs(
            os.environ.get(
                "SOTRA_PAIRS",
                ",".join(f"{s}->{t}" for s, t in DEFAULT_SOTRA_PAIRS),
            )
        )
    )
    libretranslate_langs: set[str] = field(
        default_factory=lambda: set(
            os.environ.get(
                "LIBRETRANSLATE_LANGS",
                ",".join(sorted(DEFAULT_LIBRETRANSLATE_LANGS)),
            ).split(",")
        )
    )

    @property
    def all_languages(self) -> set[str]:
        langs: set[str] = set(self.libretranslate_langs)
        for src, tgt in self.sotra_pairs:
            langs.add(src)
            langs.add(tgt)
        return langs


settings = Settings()
