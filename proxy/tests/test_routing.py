import pytest

from app.config import Settings
from app.routing import Route, plan_route, supported_languages


@pytest.fixture
def cfg() -> Settings:
    return Settings(
        sotra_pairs={
            ("hsb", "de"), ("de", "hsb"),
            ("dsb", "de"), ("de", "dsb"),
            ("hsb", "dsb"), ("dsb", "hsb"),
            ("cs", "hsb"),
        },
        libretranslate_langs={"en", "de", "cs", "pl"},
        pivot_languages=("de", "en"),
    )


class TestDirectRoutes:
    def test_sotra_direct_hsb_to_de(self, cfg):
        plan = plan_route(cfg, "hsb", "de")
        assert plan.route is Route.SOTRA
        assert plan.hops() == [("sotra", "hsb", "de")]

    def test_sotra_direct_dsb_to_hsb(self, cfg):
        plan = plan_route(cfg, "dsb", "hsb")
        assert plan.route is Route.SOTRA

    def test_libretranslate_direct_de_to_en(self, cfg):
        plan = plan_route(cfg, "de", "en")
        assert plan.route is Route.LIBRETRANSLATE
        assert plan.hops() == [("libretranslate", "de", "en")]

    def test_libretranslate_direct_cs_to_de(self, cfg):
        plan = plan_route(cfg, "cs", "de")
        assert plan.route is Route.LIBRETRANSLATE

    def test_sotra_preferred_over_libre_when_both_can(self, cfg):
        cfg.sotra_pairs.add(("cs", "de"))
        plan = plan_route(cfg, "cs", "de")
        assert plan.route is Route.SOTRA


class TestChainedRoutes:
    def test_hsb_to_en_chains_via_de(self, cfg):
        plan = plan_route(cfg, "hsb", "en")
        assert plan.route is Route.CHAIN_SOTRA_LIBRE
        assert plan.pivot == "de"
        assert plan.hops() == [
            ("sotra", "hsb", "de"),
            ("libretranslate", "de", "en"),
        ]

    def test_dsb_to_en_chains_via_de(self, cfg):
        plan = plan_route(cfg, "dsb", "en")
        assert plan.route is Route.CHAIN_SOTRA_LIBRE
        assert plan.pivot == "de"

    def test_en_to_hsb_chains_via_de(self, cfg):
        plan = plan_route(cfg, "en", "hsb")
        assert plan.route is Route.CHAIN_LIBRE_SOTRA
        assert plan.pivot == "de"
        assert plan.hops() == [
            ("libretranslate", "en", "de"),
            ("sotra", "de", "hsb"),
        ]

    def test_pl_to_dsb_chains_via_de(self, cfg):
        plan = plan_route(cfg, "pl", "dsb")
        assert plan.route is Route.CHAIN_LIBRE_SOTRA
        assert plan.pivot == "de"


class TestIdentityAndUnsupported:
    def test_identity(self, cfg):
        plan = plan_route(cfg, "de", "de")
        assert plan.route is Route.IDENTITY
        assert plan.hops() == []

    def test_unsupported_pair_yields_unsupported(self, cfg):
        cfg.sotra_pairs.clear()
        cfg.libretranslate_langs.clear()
        plan = plan_route(cfg, "hsb", "en")
        assert plan.route is Route.UNSUPPORTED

    def test_dsb_to_cs_unsupported_without_chain_path(self, cfg):
        # cs is in libretranslate, dsb is in sotra. Pivoting via de works:
        # dsb -> de (sotra) then de -> cs (libretranslate). Confirm chain.
        plan = plan_route(cfg, "dsb", "cs")
        assert plan.route is Route.CHAIN_SOTRA_LIBRE
        assert plan.pivot == "de"


class TestMatrix:
    def test_full_matrix_covers_all_task_pairs(self, cfg):
        matrix = supported_languages(cfg)
        required = [
            # scenario i: fully via sotra
            ("hsb", "de"), ("de", "hsb"), ("dsb", "hsb"), ("hsb", "dsb"),
            # scenario ii: cs -> hsb via sotra
            ("cs", "hsb"),
            # scenario iii: de -> en via libretranslate
            ("de", "en"), ("en", "de"),
            # scenario iv: hsb -> en chained
            ("hsb", "en"), ("dsb", "en"), ("en", "hsb"), ("en", "dsb"),
            # cross-slavic via libretranslate
            ("cs", "pl"), ("pl", "cs"),
        ]
        for src, tgt in required:
            assert tgt in matrix[src], f"missing {src}->{tgt} in supported matrix"
