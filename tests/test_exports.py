"""Regressões offline para exportações e configuração do frontend."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sosia.exports import export_reports, render_html, render_pdf
from sosia.webapp import make_brand, list_variants, inspect_bio


def example():
    return {
        "brand": {
            "name": "Marca Zeta",
            "handle": "marcazeta",
            "domains": ["marcazeta.com.br"],
            "display_names": ["Marca Zeta"],
            "official": {"*": ["marcazeta"]},
        },
        "meta": {"version": "1.1.0", "started_at": "2026-10-15T10:00:00+00:00", "duration_s": 3.0},
        "stats": {
            "totals": {"requests": 3, "candidates_generated": 4, "found": 1, "inconclusive": 1},
            "platforms": {"mock": {"state": "trusted", "reason": "controles válidos", "requests": 3}},
        },
        "calibrations": [{"platform": "mock", "state": "trusted", "reason": "controles válidos"}],
        "findings": [{
            "platform": "mock", "username": "marcazeta_suporte01",
            "url": "https://example.org/marcazeta_suporte01",
            "existence": "confirmed",
            "profile": {"display_name": "Suporte", "bio": 'Contato <script>alert("x")</script>.'},
            "assessment": {"priority": "ALTO", "confidence": 0.9,
                           "reasons": ["Alega oficialidade", "Pede pagamento"]},
        }, {
            "platform": "mock", "username": "marcazeta_na",
            "url": "javascript:alert(1)",
            "existence": "inconclusive", "profile": None,
            "assessment": None, "reason": "bloqueado",
        }],
    }


class ExportReportTests(unittest.TestCase):
    def test_html_has_sections_and_does_not_interpret_bio_as_markup(self):
        rendered = render_html(example())
        self.assertIn("<!doctype html>", rendered)
        self.assertIn("Saúde dos conectores", rendered)
        self.assertIn("Perfis e achados", rendered)
        self.assertIn("Marca Zeta", rendered)
        self.assertNotIn('<script>alert("x")</script>', rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn("Inconclusivos", rendered)

    def test_html_escapes_brand(self):
        data = example()
        data["brand"]["name"] = '<img src=x onerror="alert(1)">'
        rendered = render_html(data)
        self.assertIn("&lt;img", rendered)
        self.assertNotIn('<img src=x onerror=', rendered)

    def test_exports_update_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            original = folder / "case.json"
            original.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            (folder / "MANIFEST.sha256").write_text(digest + "  case.json\n", encoding="utf-8")
            paths = export_reports(example(), folder, html_report=True, pdf_report=False)
            self.assertEqual([p.name for p in paths], ["report.html"])
            values = {}
            for line in (folder / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
                digest, name = line.split("  ", 1)
                values[name] = digest
                self.assertEqual(digest, hashlib.sha256((folder / name).read_bytes()).hexdigest())
            self.assertIn("case.json", values)
            self.assertIn("report.html", values)
            export_reports(example(), folder, html_report=True, pdf_report=False)
            self.assertEqual(len((folder / "MANIFEST.sha256").read_text().splitlines()), 2)

    def test_pdf_is_valid_if_optional_dependency_exists(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("reportlab é dependência opcional para PDF")
        pdf = render_pdf(example())
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)


class FrontendInputTests(unittest.TestCase):
    def test_form_maps_allowlist_and_affixes(self):
        brand = make_brand("Marca Zeta", "@MARCAZETA",
                           "marcazeta.com.br", "@marcazeta, marcazeta_sac", "clube, cartao")
        self.assertEqual(brand.handle, "marcazeta")
        self.assertIn("marcazeta_sac", brand.official["*"])
        self.assertEqual(brand.extra_affixes, ["clube", "cartao"])

    def test_domain_rejects_url_or_path(self):
        with self.assertRaises(ValueError):
            make_brand("Marca Zeta", "marcazeta",
                       "https://marcazeta.com.br/login", "", "")

    def test_variant_generation_offline(self):
        summary, rows = list_variants("Marca Zeta", "marcazeta", "marcazeta.com.br",
                                      "marcazeta", "clube", 15)
        self.assertIn("candidatos", summary)
        self.assertGreater(len(rows), 0)
        self.assertLessEqual(len(rows), 15)
        self.assertFalse(any(row[0] == "marcazeta" for row in rows))

    def test_bio_analysis_is_explicitly_offline(self):
        summary, rows = inspect_bio("Marca Zeta", "marcazeta", "marcazeta.com.br",
                                    "marcazeta", "clube",
                                    "marcazeta_suporte", "Marca Zeta",
                                    "Suporte oficial Marca Zeta. Faça Pix da taxa.")
        self.assertIn("nenhuma consulta", summary.lower())
        self.assertTrue(isinstance(rows, list))


if __name__ == "__main__":
    unittest.main()
