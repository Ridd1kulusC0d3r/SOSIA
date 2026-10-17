import gzip
import hashlib
import http.server
import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sosia import cli
from sosia.bench.corpus import POSITIVE, POSITIVE2, build_corpus, sim_platforms
from sosia.bench.runner import run_bench
from sosia.bench.world import Behavior, MockWorld, ProfileSpec, SiteSpec
from sosia.diff import diff_cases
from sosia.model import Brand, Existence
from sosia.net import UrlLibFetcher
from sosia.report import to_csv, to_markdown, to_stix, write_case
from sosia.scanner import ScanConfig, Scanner


def sample_result():
    plats = {"cleana": sim_platforms()["cleana"]}
    prof = {"cleana": {
        "marcazeta_suporte": ProfileSpec("Marca Zeta Suporte", "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!", 5),
        "marcazeta_fas": ProfileSpec("Marca Zeta Fãs", "Perfil de fãs. Não oficial.", 5),
        POSITIVE: ProfileSpec("Ref", "Perfil de referência para calibração.", 1),
        POSITIVE2: ProfileSpec("Ref Dois", "Outro perfil de referência.", 2)}}
    w = MockWorld({"cleana": SiteSpec("cleana", Behavior.CLEAN)}, prof)
    b = Brand("Marca Zeta", "marcazeta", domains=["marcazeta.com.br"])
    return Scanner(b, plats, w, ScanConfig(budget=80, seed=1, save_raw=True, extra_candidates=["marcazeta_suporte", "marcazeta_fas"])).run()


class Reports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = sample_result()

    def test_markdown_has_transparency_sections(self):
        md = to_markdown(self.res)
        for needle in ("Saúde dos conectores", "CRITICO", "Por quê", "Descoberta além da enumeração", "Limites", "não validados" if False else "validação ao vivo"):
            self.assertIn(needle, md)

    def test_csv_roundtrip(self):
        rows = to_csv(self.res).splitlines()
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(rows[0].startswith("id,platform,username"))

    def test_stix_bundle_is_wellformed(self):
        b = to_stix(self.res)
        self.assertEqual(b["type"], "bundle")
        types = [o["type"] for o in b["objects"]]
        self.assertIn("indicator", types)
        self.assertIn("identity", types)
        ind = next(o for o in b["objects"] if o["type"] == "indicator")
        self.assertTrue(ind["pattern"].startswith("[url:value = 'https://"))
        ids = [o["id"] for o in b["objects"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_evidence_pack_manifest_matches_files(self):
        with tempfile.TemporaryDirectory() as d:
            write_case(self.res, d)
            manifest = (Path(d) / "MANIFEST.sha256").read_text().splitlines()
            self.assertTrue(manifest)
            for line in manifest:
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((Path(d) / name).read_bytes()).hexdigest(), digest, name)
            self.assertTrue(any(n.startswith("evidence/") for n in (l.split("  ", 1)[1] for l in manifest)))
            self.assertTrue(any(n.startswith("raw/") for n in (l.split("  ", 1)[1] for l in manifest)))

    def test_diff_detects_new_and_bio_change(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.json", Path(d) / "b.json"
            data = self.res.to_dict()
            old = json.loads(json.dumps(data))
            old["findings"] = [f for f in old["findings"] if f["username"] != "marcazeta_fas"]
            for f in old["findings"]:
                if f["username"] == "marcazeta_suporte":
                    f["profile"]["bio"] = "bio antiga"
            a.write_text(json.dumps(old))
            b.write_text(json.dumps(data))
            out = diff_cases(a, b)
            self.assertEqual([x["username"] for x in out["new"]], ["marcazeta_fas"])
            self.assertEqual([x["username"] for x in out["bio_changed"]], ["marcazeta_suporte"])


class Handler(http.server.BaseHTTPRequestHandler):
    hits = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.hits += 1
        if self.path == "/ok":
            self._send(200, b"hello")
        elif self.path == "/gz":
            self._send(200, gzip.compress(b"zipped"), {"Content-Encoding": "gzip"})
        elif self.path == "/redir":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/limited":
            self._send(429, b"slow down", {"Retry-After": "0"})
        elif self.path == "/ua":
            self._send(200, self.headers.get("User-Agent", "").encode())
        else:
            self._send(404, b"nope")

    def _send(self, code, body, headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Network(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.f = UrlLibFetcher(min_interval=0, retries=1, max_retry_wait=0.1, timeout=3)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_basic_statuses(self):
        self.assertEqual(self.f.get(self.base + "/ok").text, "hello")
        self.assertEqual(self.f.get(self.base + "/nope").status, 404)
        self.assertEqual(self.f.get(self.base + "/gz").text, "zipped")

    def test_redirect_final_url(self):
        r = self.f.get(self.base + "/redir")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.final_url.endswith("/ok"))

    def test_429_is_retried_once_then_returned(self):
        before = Handler.hits
        r = self.f.get(self.base + "/limited")
        self.assertEqual(r.status, 429)
        self.assertEqual(Handler.hits - before, 2)

    def test_honest_user_agent(self):
        self.assertIn("SOSIA/", self.f.get(self.base + "/ua").text)

    def test_connection_error_is_classified_not_raised(self):
        r = self.f.get("http://127.0.0.1:1/x")
        self.assertEqual(r.status, 0)
        self.assertTrue(r.error)


class CLI(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_variants_and_platform_filter(self):
        rc, out, _ = self.run_cli("variants", "Marca Zeta", "--platform", "x", "--limit", "20", "--format", "jsonl")
        self.assertEqual(rc, 0)
        rows = [json.loads(l) for l in out.splitlines()]
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(4 <= len(r["value"]) <= 15 for r in rows))

    def test_triage_offline(self):
        rc, out, _ = self.run_cli("triage", "Marca Zeta", "--domain", "marcazeta.com.br", "--username", "marcazeta_suporte",
                                  "--text", "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["assessment"]["priority"], "CRITICO")

    def test_init_and_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sosia.toml"
            self.assertEqual(self.run_cli("init", str(p))[0], 0)
            self.assertEqual(self.run_cli("init", str(p))[0], 2)               # não sobrescreve
            rc, out, _ = self.run_cli("variants", "-c", str(p), "--limit", "5")
            self.assertEqual(rc, 0)
            self.assertNotIn("marcazeta_sac\t", out)                            # allowlist respeitada

    def test_eval_sample_file(self):
        rc, out, _ = self.run_cli("eval", str(ROOT / "examples" / "labeled_sample.jsonl"), "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["n"], 4)
        self.assertEqual(data["critical_vs_scam"]["tp"], 1)
        self.assertEqual(data["critical_vs_scam"]["fp"], 0)

    def test_fit_priors(self):
        with tempfile.TemporaryDirectory() as d:
            al, out = Path(d) / "al.txt", Path(d) / "p.json"
            al.write_text("marcazeta_oficial\nmarcazeta_suporte\nmarcazet4\nalgo_sem_relacao\n")
            rc, _, err = self.run_cli("fit-priors", "marcazeta", str(al), "-o", str(out))
            self.assertEqual(rc, 0)
            data = json.loads(out.read_text())
            self.assertEqual(data["n_matched"], 3)
            self.assertEqual(data["unmatched"], ["algo_sem_relacao"])
            self.assertGreater(data["masses"]["affix_authority"], data["masses"]["vowel_swap"])
            rc, out2, _ = self.run_cli("variants", "marcazeta", "--priors", str(out), "--limit", "3")
            self.assertEqual(rc, 0)

    def test_unknown_platform_is_usage_error(self):
        rc, _, err = self.run_cli("variants", "x", "--platform", "naoexiste")
        self.assertEqual(rc, 2)


class BenchSmoke(unittest.TestCase):
    def test_quick_bench_is_deterministic_and_wellformed(self):
        a = run_bench(seed=3, quick=True)
        b = run_bench(seed=3, quick=True)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        ex = a["existence"]["overall"]
        self.assertEqual(ex["sosia"]["fp"], 0)
        self.assertEqual(ex["sosia"]["fn_silent"], 0)
        self.assertGreater(ex["naive_status"]["fp"], 100)
        self.assertEqual(ex["sosia"]["coverage_pct"], 100.0)

    def test_corpus_split_and_unrelated_ceiling(self):
        cases = build_corpus(seed=1, n_aliases=30)
        self.assertEqual({c.split for c in cases}, {"dev", "test"})
        self.assertTrue(any(a.cls == "unrelated" for c in cases for a in c.aliases))


if __name__ == "__main__":
    unittest.main()


class WatchTests(unittest.TestCase):
    def case(self, bio, extra=None, state="trusted"):
        plats = {"cleana": sim_platforms()["cleana"]}
        prof = {"cleana": {
            "marcazeta_suporte": ProfileSpec("Marca Zeta Suporte", bio, 5),
            POSITIVE: ProfileSpec("Ref", "Perfil de referência para calibração.", 1),
            POSITIVE2: ProfileSpec("Ref Dois", "Outro perfil de referência.", 2)}}
        prof["cleana"].update(extra or {})
        w = MockWorld({"cleana": SiteSpec("cleana", Behavior.CLEAN)}, prof)
        b = Brand("Marca Zeta", "marcazeta", domains=["marcazeta.com.br"])
        cfg = ScanConfig(budget=60, seed=1, extra_candidates=["marcazeta_suporte", "marcazeta_fas"])
        d = Scanner(b, plats, w, cfg).run().to_dict()
        d["calibrations"][0]["state"] = state
        return d

    def test_baseline_then_events(self):
        from sosia.watch import exit_code, watch_step
        scam = "Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!"
        with tempfile.TemporaryDirectory() as d:
            ev, base = watch_step(self.case("Perfil oficial Marca Zeta, novidades."), d)
            self.assertTrue(base)
            self.assertEqual(ev, [])
            ev, base = watch_step(self.case(scam, extra={"marcazeta_fas": ProfileSpec("Marca Zeta Fãs", "Fãs. Não oficial.", 1)}), d)
            kinds = {(e["event"], e["username"]) for e in ev}
            self.assertIn(("new_profile", "marcazeta_fas"), kinds)
            self.assertIn(("escalated", "marcazeta_suporte"), kinds)
            self.assertIn(("profile_changed", "marcazeta_suporte"), kinds)
            self.assertEqual(exit_code(ev), 20)
            self.assertTrue((Path(d) / "alerts.jsonl").exists())
            self.assertEqual(len(list((Path(d) / "history").glob("*.json"))), 2)

    def test_gone_and_connector_loss_are_flagged(self):
        from sosia.watch import compute_events, exit_code
        a = self.case("Suporte oficial Marca Zeta. Chame no WhatsApp. Reembolso via Pix hoje!")
        b = self.case("x", state="blocked")
        b["findings"] = []
        ev = compute_events(a, b)
        kinds = {e["event"] for e in ev}
        self.assertTrue({"profile_gone", "connector_change"} <= kinds)
        conn = next(e for e in ev if e["event"] == "connector_change")
        self.assertIn("cobertura perdida", conn["note"])
        self.assertEqual(exit_code(ev), 10)

    def test_no_changes_no_events(self):
        from sosia.watch import compute_events
        a = self.case("Perfil oficial Marca Zeta, novidades.")
        self.assertEqual(compute_events(a, json.loads(json.dumps(a))), [])


class DiscoveryTests(unittest.TestCase):
    class Fake:
        def __init__(self, n_contains):
            self.n = n_contains

        def get(self, url, headers=None):
            from sosia.net import Response
            if "searchActors" in url:
                acts = [{"handle": f"zeta{i}.bsky.social", "displayName": f"Zeta {i}", "description": "oi"} for i in range(self.n)]
                acts += [{"handle": "joao.bsky.social", "displayName": "Joao", "description": "x"},
                         {"handle": "zeta.com.br", "displayName": "Zeta", "description": "oficial"}]
                return Response(url, 200, url, {}, json.dumps({"actors": acts}).encode())
            return Response(url, 200, url, {}, json.dumps({"accounts": []}).encode())

    def test_discover_classifies_and_flags_saturation(self):
        from sosia.discovery import discover, estimate_ambiguity, handle_class, local_part
        accs = discover("zeta", self.Fake(5), ())
        classes = [handle_class("zeta", local_part(a)) if local_part(a) else "custom_domain" for a in accs]
        self.assertEqual(classes.count("contains"), 5)
        self.assertIn("custom_domain", classes)
        self.assertIn("unrelated", classes)
        self.assertFalse(estimate_ambiguity("zeta", accs)["saturated"])
        big = estimate_ambiguity("zeta", discover("zeta", self.Fake(60), ()))
        self.assertTrue(big["saturated"])
        self.assertIn("ambiguous = true", big["advice"])
