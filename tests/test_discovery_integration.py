import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sosia.bench.corpus import POSITIVE, POSITIVE2, sim_platforms
from sosia.bench.world import Behavior, MockWorld, ProfileSpec, SiteSpec
from sosia.model import Brand, Existence, Priority
from sosia.net import Response
from sosia.report import to_markdown
from sosia.scanner import ScanConfig, Scanner

SCAM = "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!"


class Router:
    """Busca nativa -> respostas canned; todo o resto -> mundo simulado."""

    def __init__(self, world, n_contains=3, fail=False):
        self.world, self.n, self.fail = world, n_contains, fail

    def get(self, url, headers=None):
        if "searchActors" in url or "/api/v2/search" in url:
            if self.fail:
                return Response(url, 0, url, error="Timeout: x")
            if "searchActors" in url:
                acts = [{"handle": f"marcazeta_clube{i}.bsky.social", "displayName": "x", "description": ""} for i in range(self.n)]
                return Response(url, 200, url, {}, json.dumps({"actors": acts}).encode())
            return Response(url, 200, url, {}, json.dumps({"accounts": []}).encode())
        return self.world.get(url, headers)


def build(n_contains=3, fail=False, ambiguous=False, found_user="marcazeta_clube0"):
    plats = {"cleana": sim_platforms()["cleana"]}
    prof = {"cleana": {found_user: ProfileSpec("Marca Zeta Suporte", SCAM, 5),
                       POSITIVE: ProfileSpec("Ref", "Perfil de referência para calibração.", 1),
                       POSITIVE2: ProfileSpec("Ref Dois", "Outro perfil de referência.", 2)}}
    w = MockWorld({"cleana": SiteSpec("cleana", Behavior.CLEAN)}, prof)
    brand = Brand("Marca Zeta", "marcazeta", domains=["marcazeta.com.br"], ambiguous=ambiguous)
    cfg = ScanConfig(budget=30, seed=1, discover=True)
    return Scanner(brand, plats, Router(w, n_contains, fail), cfg).run(), cfg


class DiscoveryIntegration(unittest.TestCase):
    def test_discovered_handle_outside_variant_space_is_probed_and_found(self):
        res, cfg = build()
        self.assertTrue(res.meta["discovery"]["ok"])
        self.assertEqual(res.meta["discovery"]["candidates_added"], 3)
        self.assertIn("marcazeta_clube0", cfg.extra_candidates)
        hit = [f for f in res.findings if f.username == "marcazeta_clube0"]
        self.assertEqual(len(hit), 1)
        self.assertEqual(hit[0].existence, Existence.CONFIRMED)
        self.assertEqual(hit[0].assessment.priority, Priority.CRITICAL)
        self.assertFalse(res.meta["discovery"]["saturated"])

    def test_without_discovery_the_same_handle_is_missed(self):
        res, cfg = build()
        plats = {"cleana": sim_platforms()["cleana"]}
        w = MockWorld({"cleana": SiteSpec("cleana", Behavior.CLEAN)},
                      {"cleana": {"marcazeta_clube0": ProfileSpec("x", SCAM, 1), POSITIVE: ProfileSpec("R", "ref ref ref", 1),
                                  POSITIVE2: ProfileSpec("R2", "outro ref", 1)}})
        off = Scanner(Brand("Marca Zeta", "marcazeta"), plats, w, ScanConfig(budget=30, seed=1)).run()
        self.assertNotIn("marcazeta_clube0", {f.username for f in off.findings})
        self.assertIsNone(off.meta["discovery"])

    def test_saturated_brand_turns_ambiguous_and_caps_priority(self):
        res, _ = build(n_contains=60)
        d = res.meta["discovery"]
        self.assertTrue(d["saturated"] and d["ambiguous_auto"])
        top = next(f for f in res.findings if f.username == "marcazeta_clube0")
        self.assertEqual(top.assessment.priority, Priority.HIGH)               # CRÍTICO limitado pela ambiguidade
        self.assertTrue(any("ambígua" in r for r in top.assessment.reasons))
        self.assertIn("saturada", to_markdown(res).lower())

    def test_search_near_cap_is_saturated_even_without_brand_in_handles(self):
        from sosia.discovery import estimate_ambiguity
        accs = [{"platform": "bluesky", "handle": f"pessoa{i}.bsky.social"} for i in range(160)]
        e = estimate_ambiguity("washington", accs)
        self.assertEqual(e["handles_containing_brand"], 0)
        self.assertTrue(e["saturated"])

    def test_user_declared_ambiguity_is_not_reported_as_auto(self):
        res, _ = build(n_contains=60, ambiguous=True)
        self.assertFalse(res.meta["discovery"]["ambiguous_auto"])

    def test_discovery_failure_never_breaks_the_scan(self):
        res, _ = build(fail=True)
        self.assertIsNotNone(res.meta["discovery"])
        self.assertEqual(res.stats["totals"]["platforms_usable"], 1)
        self.assertFalse(res.meta["discovery"]["ok"])
        self.assertIn("indisponível", res.meta["discovery"]["error"])
        self.assertIn("Descoberta indisponível", to_markdown(res))


if __name__ == "__main__":
    unittest.main()
