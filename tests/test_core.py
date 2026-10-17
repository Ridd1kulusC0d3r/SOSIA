import json
import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sosia.bench.corpus import POSITIVE, POSITIVE2, SITES, build_corpus, build_world, sim_platforms
from sosia.bench.world import Behavior, MockWorld, ProfileSpec, SiteSpec
from sosia.calibrate import CalState, calibrate, random_valid_username
from sosia.checks import Kind, classify, get_path
from sosia.model import Brand, Existence, Priority
from sosia.net import Response
from sosia.platforms import load_platforms
from sosia.profiles import Profile, extract_profile, find_links
from sosia.scanner import ScanConfig, Scanner
from sosia.scoring import assess
from sosia.signals import analyze_bio, deobfuscate, registrable
from sosia.textutil import dl_distance, norm_text, similarity, skeleton
from sosia.variants import Constraint, VariantEngine, display_variants


def brand(**kw):
    kw.setdefault("domains", ["marcazeta.com.br"])
    return Brand(name="Marca Zeta", handle="marcazeta", **kw)


class TextUtil(unittest.TestCase):
    def test_skeleton_folds_visual_tricks(self):
        self.assertEqual(skeleton("rnarcazet4"), skeleton("marcazeta"))
        self.assertEqual(skeleton("Mаrcazeta"), skeleton("marcazeta"))           # cirílico а
        self.assertEqual(skeleton("marca_zeta"), skeleton("marca.zeta"))
        self.assertEqual(skeleton("marc​azeta"), skeleton("marcazeta"))          # zero-width

    def test_similarity_bounds(self):
        self.assertEqual(similarity("marcazeta", "marcazeta"), 1.0)
        self.assertGreater(similarity("marcazeta", "marcazeta_suporte"), 0.85)
        self.assertLess(similarity("marcazeta", "padariadojoao"), 0.4)

    def test_dl_distance_transposition_is_one(self):
        self.assertEqual(dl_distance("marca", "mraca"), 1)
        self.assertEqual(dl_distance("", "abc"), 3)

    def test_norm_text_strips_accents(self):
        self.assertEqual(norm_text("PROMOÇÕES  Atenção"), "promocoes atencao")


class Variants(unittest.TestCase):
    def setUp(self):
        self.vs = VariantEngine("marcazeta").generate()
        self.by = {v.value: v for v in self.vs}

    def test_expected_families_present(self):
        for expected in ["marcazeta_oficial", "suporte.marcazeta", "marcazet4", "rnarcazeta", "marca_zeta",
                         "marcazeta_pix", "marcazeta_suporte01", "marcazeta_ofical", "mrcazeta", "marcazeeta", "macrazeta"]:
            self.assertIn(expected, self.by, expected)

    def test_base_and_official_excluded(self):
        self.assertNotIn("marcazeta", self.by)
        vs = VariantEngine("marcazeta").generate(exclude=["marcazeta_oficial"])
        self.assertNotIn("marcazeta_oficial", {v.value for v in vs})

    def test_constraint_respected(self):
        c = Constraint(re.compile(r"^[a-z0-9_]{4,15}$"), 4, 15)
        vs = VariantEngine("marcazeta").generate(constraint=c)
        self.assertTrue(vs)
        self.assertTrue(all(c.valid(v.value) for v in vs))
        self.assertNotIn("marca.zeta", {v.value for v in vs})

    def test_small_families_not_starved(self):
        top = {v.value for v in self.vs[:60]}
        self.assertTrue({"mrcazeta", "macrazeta", "marcazet4"} <= top)   # omissão/transposição/homóglifo no topo

    def test_deterministic_and_unique(self):
        again = VariantEngine("marcazeta").generate()
        self.assertEqual([v.value for v in again], [v.value for v in self.vs])
        self.assertEqual(len(self.by), len(self.vs))

    def test_extra_affixes_and_masses_override(self):
        vs = VariantEngine("marcazeta", extra_affixes=["cartao"]).generate()
        self.assertIn("marcazeta_cartao", {v.value for v in vs})
        only_homo = VariantEngine("marcazeta", masses={"homoglyph": 50.0}).generate()
        self.assertEqual(only_homo[0].families, {"homoglyph"})

    def test_empty_base_rejected(self):
        with self.assertRaises(ValueError):
            VariantEngine("***")

    def test_display_variants_include_confusable_and_affix(self):
        dv = {d["family"] for d in display_variants("Marca Zeta")}
        self.assertTrue({"display_affix", "display_unicode_confusable"} <= dv)


def resp(status=200, body="", url="https://x.sim/u", final=None, headers=None):
    return Response(url, status, final or url, headers or {}, body.encode() if isinstance(body, str) else body)


class Checks(unittest.TestCase):
    def setUp(self):
        self.ps = load_platforms()

    def test_status_code_check(self):
        p = self.ps["pinterest"]
        self.assertEqual(classify(p, resp(200, "ok"), "x").kind, Kind.FOUND)
        self.assertEqual(classify(p, resp(404), "x").kind, Kind.MISSING)
        self.assertEqual(classify(p, resp(429), "x").kind, Kind.BLOCKED)
        self.assertEqual(classify(p, resp(418), "x").kind, Kind.UNKNOWN)

    def test_rate_limit_never_becomes_absence(self):
        for st in (403, 429, 503, 999):
            self.assertEqual(classify(self.ps["youtube"], resp(st), "x").kind, Kind.BLOCKED)

    def test_captcha_page_is_blocked_not_found(self):
        v = classify(self.ps["pinterest"], resp(200, "<title>Just a moment...</title>"), "x")
        self.assertEqual(v.kind, Kind.BLOCKED)

    def test_json_check(self):
        p = self.ps["github"]
        self.assertEqual(classify(p, resp(200, '{"login":"a"}'), "a").kind, Kind.FOUND)
        self.assertEqual(classify(p, resp(404, '{"message":"Not Found"}'), "a").kind, Kind.MISSING)
        self.assertEqual(classify(p, resp(200, "<html>"), "a").kind, Kind.UNKNOWN)
        g = self.ps["gitlab"]
        self.assertEqual(classify(g, resp(200, "[]"), "a").kind, Kind.MISSING)
        self.assertEqual(classify(g, resp(200, '[{"id":1}]'), "a").kind, Kind.FOUND)

    def test_message_check_with_username_placeholder(self):
        p = self.ps["tiktok"]
        self.assertEqual(classify(p, resp(200, '{"uniqueId":"bob"}'), "bob").kind, Kind.FOUND)
        self.assertEqual(classify(p, resp(200, '{"statusCode":10221}'), "bob").kind, Kind.MISSING)
        self.assertEqual(classify(p, resp(200, "<html></html>"), "bob").kind, Kind.UNKNOWN)

    def test_network_error(self):
        r = Response("u", 0, "u", error="TimeoutError: x")
        self.assertEqual(classify(self.ps["github"], r, "a").kind, Kind.ERROR)

    def test_get_path(self):
        self.assertEqual(get_path({"a": [{"b": 5}]}, "a.0.b"), 5)
        self.assertIsNone(get_path({"a": 1}, "a.b"))

    def test_all_builtin_connectors_load_and_are_flagged_unverified(self):
        self.assertGreaterEqual(len(self.ps), 15)
        self.assertTrue(all(p.verified_on is None for p in self.ps.values()))
        for p in self.ps.values():
            self.assertIn("{u}", p.url)
            u = random_valid_username(p, random.Random(1))
            self.assertIsNotNone(u, p.id)
            self.assertTrue(p.valid_username(u))


def world_for(*specs, profiles=None, seed=1):
    sites = {s.id: s for s in specs}
    prof = {s.id: {POSITIVE: ProfileSpec("Ref", "Perfil de referência para teste de calibração.", 1),
                   POSITIVE2: ProfileSpec("Ref Dois", "Outro perfil de referência com texto diferente.", 2)} for s in specs}
    for sid, d in (profiles or {}).items():
        prof[sid].update(d)
    return MockWorld(sites, prof, seed)


class Calibration(unittest.TestCase):
    def cal(self, behavior, **kw):
        plats = sim_platforms()
        site = {"clean": "cleana", "soft404": "softpos", "spa_shell": "spashell", "login_wall": "loginwall",
                "ratelimit": "ratelimit", "captcha": "captcha", "api_json": "apijson", "soft404_msg": "softmsg",
                "flaky": "flaky"}[behavior]
        w = world_for(SiteSpec(site, Behavior(behavior), **kw))
        return calibrate(plats[site], w, rng=random.Random(3))

    def test_states(self):
        self.assertEqual(self.cal("clean").state, CalState.TRUSTED)
        self.assertEqual(self.cal("api_json").state, CalState.TRUSTED)
        self.assertEqual(self.cal("soft404_msg").state, CalState.TRUSTED)
        self.assertEqual(self.cal("soft404").state, CalState.DIFFERENTIAL)
        self.assertEqual(self.cal("spa_shell").state, CalState.SOFT404)
        self.assertEqual(self.cal("login_wall").state, CalState.SOFT404)
        self.assertEqual(self.cal("ratelimit", after=1).state, CalState.BLOCKED)
        self.assertEqual(self.cal("captcha", after=1).state, CalState.BLOCKED)

    def test_soft404_without_positive_control_is_discarded(self):
        plats = sim_platforms()
        w = world_for(SiteSpec("softnopos", Behavior.SOFT404))
        cal = calibrate(plats["softnopos"], w, rng=random.Random(3))
        self.assertEqual(cal.state, CalState.SOFT404)
        self.assertFalse(cal.usable)

    def test_flaky_is_survivable_thanks_to_retry(self):
        states = {self.cal("flaky", flaky_p=0.12).state for _ in range(1)}
        self.assertTrue(states <= {CalState.TRUSTED, CalState.TRUSTED_NO_POSITIVE, CalState.BLOCKED})

    def test_random_controls_are_valid_for_platform(self):
        rng = random.Random(0)
        for p in load_platforms().values():
            for _ in range(20):
                self.assertTrue(p.valid_username(random_valid_username(p, rng)))

    def test_negative_controls_recorded(self):
        c = self.cal("clean")
        self.assertEqual(len(c.negatives), 3)
        self.assertIsNotNone(c.positive)
        self.assertEqual(c.requests, 4)


class Signals(unittest.TestCase):
    def rep(self, bio, name="Marca Zeta"):
        return analyze_bio(Profile(display_name=name, bio=bio, links=find_links(bio)), brand())

    def test_scam_bio_is_strong(self):
        r = self.rep("Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!")
        self.assertEqual(r.abuse_level, "strong")
        self.assertIn("financial_ask", r.groups)
        self.assertIn("isolation", r.levers)

    def test_negated_mentions_do_not_count(self):
        r = self.rep("Atendimento oficial Marca Zeta. Nunca pedimos senha ou Pix por aqui.")
        self.assertEqual(r.abuse_level, "none")
        self.assertTrue(any(m.id == "security_notice" for m in r.mitigators))

    def test_payment_method_mention_is_not_a_request(self):
        r = self.rep("Revenda autorizada. Aceitamos Pix e cartão. Atendimento via WhatsApp.")
        self.assertNotIn("financial_ask", r.groups)
        self.assertLess(["none", "weak", "moderate", "strong"].index(r.abuse_level), 3)

    def test_obfuscation_is_decoded(self):
        self.assertEqual(deobfuscate("faca o p1x agora 123"), "faca o pix agora 123")
        r = self.rep("Atendimento Marca Zeta 24h – p1x ou boleto")
        self.assertIn("financial_ask", r.groups)

    def test_disclaimer_detected_and_oficial_negated(self):
        r = self.rep("Perfil de fãs da Marca Zeta. Não oficial. Humor e memes.")
        self.assertTrue(r.disclaimed)
        self.assertNotIn("claims_official", {s.id for s in r.signals})

    def test_lookalike_domain_and_shortener(self):
        r = self.rep("Promoção Marca Zeta só hoje! marcazeta-promo.com e bit.ly/abc123")
        classes = {d["class"] for d in r.domains}
        self.assertIn("lookalike_domain", classes)
        self.assertIn("shortener", classes)

    def test_authorized_domain_is_only_a_claim(self):
        r = self.rep("Siga a gente em marcazeta.com.br")
        self.assertTrue(r.links_authorized_domain)
        self.assertEqual(r.abuse_level, "none")

    def test_registrable(self):
        self.assertEqual(registrable("www.loja.marcazeta.com.br"), "marcazeta.com.br")
        self.assertEqual(registrable("sub.example.org"), "example.org")

    def test_empty_bio(self):
        r = analyze_bio(Profile(display_name="X", bio=None), brand())
        self.assertFalse(r.bio_available)
        self.assertEqual(r.abuse_level, "none")


class Scoring(unittest.TestCase):
    def prio(self, username, bio, name="Marca Zeta", conf=0.95, b=None):
        b = b or brand()
        p = Profile(display_name=name, bio=bio, links=find_links(bio or ""))
        rep = analyze_bio(p, b)
        return assess(b, "instagram", username, similarity(b.handle, username), conf, p, rep)

    def test_critical_needs_independent_evidence(self):
        a = self.prio("marcazeta_suporte", "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!")
        self.assertEqual(a.priority, Priority.CRITICAL)
        self.assertEqual(a.severity, "financeiro")

    def test_single_keyword_is_not_critical(self):
        a = self.prio("marcazeta_suporte", "Suporte Marca Zeta. Fale com a gente no direct.")
        self.assertNotEqual(a.priority, Priority.CRITICAL)
        b = self.prio("marcazeta_loja", "Aceitamos Pix. Marca Zeta")
        self.assertNotEqual(b.priority, Priority.CRITICAL)

    def test_security_notice_not_critical(self):
        a = self.prio("marcazeta_sac2", "Atendimento oficial Marca Zeta. Nunca pedimos senha ou Pix por aqui.")
        self.assertNotEqual(a.priority, Priority.CRITICAL)

    def test_authorized_handle_is_info(self):
        b = brand(official={"*": {"marcazeta_sac"}})
        a = self.prio("marcazeta_sac", "Suporte oficial. Pix. WhatsApp. senha", b=b)
        self.assertEqual(a.priority, Priority.INFO)
        self.assertEqual(a.affiliation, "authorized")

    def test_no_bio_caps_at_high_and_flags_review(self):
        a = self.prio("marcazeta_oficial", None, name="Marca Zeta Oficial")
        self.assertLessEqual(a.priority.rank, Priority.HIGH.rank)
        self.assertLess(a.confidence, 0.8)

    def test_differential_existence_cannot_be_critical(self):
        a = self.prio("marcazeta_suporte", "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!", conf=0.65)
        self.assertEqual(a.priority, Priority.HIGH)
        self.assertTrue(a.needs_review)

    def test_fan_with_disclaimer_is_not_critical_even_with_cues(self):
        a = self.prio("marcazeta_fas", "Perfil de fãs, não oficial. Chame no WhatsApp para parcerias. Sorteio!")
        self.assertNotEqual(a.priority, Priority.CRITICAL)

    def test_homonym_with_unrelated_bio_is_low(self):
        a = self.prio("marcazeta_pet", "Pet shop da Marcia. Banho e tosa.", name="Marcia Pet")
        self.assertLessEqual(a.priority.rank, Priority.LOW.rank)

    def test_scam_language_unrelated_to_brand_is_not_an_alert(self):
        # regressão do bench real: host de sorteio / doação via Pix não é impersonação da marca
        a = self.prio("joana_artes", "Sorteio todo mês! Me chama no WhatsApp. Pix: livepix.gg/joana", name="Joana Artes")
        self.assertEqual(a.priority, Priority.LOW)
        self.assertIn("não é impersonação desta marca", " ".join(a.reasons))

    def test_lone_lookalike_domain_is_medium_not_high(self):
        a = self.prio("marcazeta_news", "Notícias sobre a Marca Zeta em marcazeta-noticias.com", name="Marca Zeta News")
        self.assertLessEqual(a.priority.rank, Priority.MEDIUM.rank)

    def test_brand_named_only_as_payment_method_is_not_high(self):
        # regressão do bench real (hold-out #3): "Pix (Nubank)" na bio de uma pessoa
        a = self.prio("joana_artes", "Ilustradora. Pix: 123.456 (Marca Zeta)", name="Joana Artes")
        self.assertLessEqual(a.priority.rank, Priority.MEDIUM.rank)

    def test_sibling_tld_is_not_lookalike(self):
        r = analyze_bio(Profile(display_name="Marca Zeta", bio="Site: marcazeta.com", links=["marcazeta.com"]), brand())
        self.assertIn("sibling_tld", {d["class"] for d in r.domains})
        self.assertNotIn("lookalike_link", r.groups)

    def test_reasons_are_explainable(self):
        a = self.prio("marcazeta_suporte", "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!")
        self.assertTrue(any("CRÍTICO" in r for r in a.reasons))
        self.assertTrue(any("alavancas" in r for r in a.reasons))


class ProfilesExtraction(unittest.TestCase):
    def test_html_meta(self):
        p = load_platforms()["telegram"]
        html = '<meta property="og:title" content="Marca &amp; Zeta"><meta property="og:description" content="Bio aqui t.me/x">'
        pr = extract_profile(p, resp(200, html))
        self.assertEqual(pr.display_name, "Marca & Zeta")
        self.assertEqual(pr.bio, "Bio aqui t.me/x")
        self.assertTrue(pr.links)

    def test_platform_placeholder_bio_is_not_a_bio(self):
        p = load_platforms()["telegram"]
        html = '<meta property="og:title" content="Fulano"><meta property="og:description" content="You can contact @fulano right away.">'
        pr = extract_profile(p, resp(200, html))
        self.assertEqual(pr.display_name, "Fulano")
        self.assertIsNone(pr.bio)
        self.assertFalse(pr.bio_available)

    def test_json_map_and_html_field(self):
        p = load_platforms()["mastodon"]
        body = json.dumps({"display_name": "Zeta", "note": "<p>Oi <a href='x'>link</a></p>", "followers_count": 12})
        pr = extract_profile(p, resp(200, body))
        self.assertEqual(pr.bio, "Oi link")
        self.assertEqual(pr.followers, 12)


class ScannerE2E(unittest.TestCase):
    def run_scan(self, behavior, aliases, **kw):
        sid = kw.pop("site")
        plats = {sid: sim_platforms()[sid]}
        spec = SiteSpec(sid, behavior, **kw)
        profiles = {a: ProfileSpec("Marca Zeta Oficial", "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!", 3) for a in aliases}
        profiles["marcazeta"] = ProfileSpec("Marca Zeta", "Perfil oficial", 1)
        w = world_for(spec, profiles={sid: profiles})
        b = brand(official={"*": {"marcazeta"}})
        cfg = ScanConfig(budget=120, seed=5, extra_candidates=aliases, record_probed=True, canary_every=10, shuffle_seed=5)
        return Scanner(b, plats, w, cfg).run(), w

    def test_clean_site_finds_and_triages(self):
        res, _ = self.run_scan(Behavior.CLEAN, ["marcazeta_oficial", "marcazeta_suporte"], site="cleana")
        hits = [f for f in res.findings if f.existence == Existence.CONFIRMED]
        self.assertEqual({f.username for f in hits}, {"marcazeta_oficial", "marcazeta_suporte"})
        self.assertTrue(all(f.assessment.priority == Priority.CRITICAL for f in hits))
        self.assertTrue(all(f.evidence["canary_validated"] for f in hits))
        self.assertNotIn("marcazeta", {f.username for f in res.findings})            # allowlist

    def test_soft404_does_not_flood_false_positives(self):
        res, _ = self.run_scan(Behavior.SOFT404, ["marcazeta_oficial"], site="softpos")
        found = {f.username for f in res.findings if f.existence in (Existence.CONFIRMED, Existence.PROBABLE)}
        self.assertEqual(found, {"marcazeta_oficial"})
        self.assertEqual(res.calibrations[0].state, CalState.DIFFERENTIAL)
        top = res.findings[0].assessment
        self.assertEqual(top.priority, Priority.HIGH)                                  # existência só "provável"

    def test_spa_shell_is_inconclusive_not_flagged(self):
        res, w = self.run_scan(Behavior.SPA_SHELL, ["marcazeta_oficial"], site="spashell")
        self.assertFalse(res.calibrations[0].usable)
        self.assertEqual([f for f in res.findings if f.existence != Existence.INCONCLUSIVE], [])
        self.assertLessEqual(res.stats["totals"]["requests"], 8)                        # não gasta orçamento

    def test_ratelimit_midrun_turns_into_inconclusive_with_reason(self):
        res, _ = self.run_scan(Behavior.RATELIMIT, ["marcazeta_oficial"], site="ratelimit", after=30)
        st = res.stats["platforms"]["ratelimit"]
        self.assertTrue(st["midrun"] or st["state"] == "degraded")
        self.assertGreater(st["skipped"], 0)

    def test_drift_triggers_canary_and_recalibration(self):
        res, _ = self.run_scan(Behavior.DRIFT, ["marcazeta_oficial", "marcazeta_suporte"], site="drift", after=40)
        st = res.stats["platforms"]["drift"]
        self.assertGreaterEqual(st["recalibrations"], 1)
        found = {f.username for f in res.findings if f.existence in (Existence.CONFIRMED, Existence.PROBABLE)}
        self.assertEqual(found, {"marcazeta_oficial", "marcazeta_suporte"})            # sem falsos positivos pós-drift

    def test_captcha_midrun_not_mistaken_for_profile(self):
        res, _ = self.run_scan(Behavior.CAPTCHA, ["marcazeta_oficial"], site="captcha", after=30)
        found = {f.username for f in res.findings if f.existence in (Existence.CONFIRMED, Existence.PROBABLE)}
        self.assertTrue(found <= {"marcazeta_oficial"})

    def test_seeded_runs_are_reproducible(self):
        a, _ = self.run_scan(Behavior.CLEAN, ["marcazeta_oficial"], site="cleana")
        b, _ = self.run_scan(Behavior.CLEAN, ["marcazeta_oficial"], site="cleana")
        self.assertEqual([f.username for f in a.sorted_findings()], [f.username for f in b.sorted_findings()])
        self.assertEqual(a.stats["totals"]["requests"], b.stats["totals"]["requests"])


if __name__ == "__main__":
    unittest.main()
