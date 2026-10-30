import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("fetch_achievements", ROOT / "scripts" / "fetch_achievements.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "data" / "achievements.json"

    def run_fetch(self, scrape, token=None):
        with patch.object(fetch, "OUT_PATH", str(self.out)), patch.object(fetch, "TOKEN", token), \
                patch.object(fetch, "scrape_earned", side_effect=scrape):
            fetch.main()
        return json.loads(self.out.read_text(encoding="utf-8"))

    def test_success_replaces_removed_and_downgraded_badges(self):
        self.run_fetch([{"pull-shark": 3, "quickdraw": 1}])
        result = self.run_fetch([{"pull-shark": 2}])
        self.assertTrue(result["available"])
        self.assertEqual(result["badges"]["pull-shark"]["tier"], 2)
        self.assertEqual(result["badges"]["quickdraw"]["tier"], 0)
        self.assertEqual(result["earned_at"], result["generated_at"])

    def test_failed_scrape_hides_old_badges_and_never_marks_them_fresh(self):
        self.run_fetch([{"pull-shark": 3}])
        result = self.run_fetch(RuntimeError("unavailable"))
        self.assertFalse(result["available"])
        self.assertIsNone(result["earned_at"])
        self.assertEqual(result["badges"], {})

    def test_public_scope_is_explicit_for_prs_and_repositories(self):
        responses = [{"search": {"issueCount": 0, "nodes": [],
                                 "pageInfo": {"hasNextPage": False}}},
                     {"user": {"repositories": {"nodes": []}}}]
        with patch.object(fetch, "graphql", side_effect=responses) as graphql:
            self.assertEqual(fetch.merged_pr_stats(), (0, 0))
            self.assertEqual(fetch.top_repo(), (None, 0))
        self.assertIn("is:public", graphql.call_args_list[0].kwargs["q"])
        self.assertIn("privacy: PUBLIC", graphql.call_args_list[1].args[0])

    def test_metric_failure_keeps_values_unknown(self):
        with patch.object(fetch, "OUT_PATH", str(self.out)), patch.object(fetch, "TOKEN", "token"), \
                patch.object(fetch, "scrape_earned", return_value={"pull-shark": 2}), \
                patch.object(fetch, "merged_pr_stats", side_effect=RuntimeError("unavailable")), \
                patch.object(fetch, "top_repo", side_effect=RuntimeError("unavailable")):
            fetch.main()
        badges = json.loads(self.out.read_text(encoding="utf-8"))["badges"]
        self.assertIsNone(badges["pull-shark"]["value"])
        self.assertIsNone(badges["public-sponsor"]["value"])
        self.assertIsNone(badges["galaxy-brain"]["value"])


class RenderTests(unittest.TestCase):
    def test_unavailable_badges_are_not_rendered_as_locked_or_fresh(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for directory in ("scripts", "data", "assets"):
                (root / directory).mkdir()
            for name in ("term.py", "render_achievements.py"):
                shutil.copy(ROOT / "scripts" / name, root / "scripts" / name)
            shutil.copy(ROOT / "data" / "contributions.json", root / "data" / "contributions.json")
            (root / "data" / "achievements.json").write_text(json.dumps({
                "available": False, "earned_at": None, "generated_at": "2026-10-31T00:00:00Z", "badges": {}
            }), encoding="utf-8")
            subprocess.run([sys.executable, str(root / "scripts" / "render_achievements.py")], check=True)
            svg = (root / "assets" / "achievements.svg").read_text(encoding="utf-8")
            ET.fromstring(svg)
            self.assertIn("GitHub achievements unavailable", svg)
            self.assertNotIn("0/0", svg)
            self.assertNotIn("updated Oct 31", svg)

    def test_repository_name_is_escaped_in_svg(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for directory in ("scripts", "data", "assets"):
                (root / directory).mkdir()
            for name in ("term.py", "render_achievements.py"):
                shutil.copy(ROOT / "scripts" / name, root / "scripts" / name)
            shutil.copy(ROOT / "data" / "contributions.json", root / "data" / "contributions.json")
            (root / "data" / "achievements.json").write_text(json.dumps({
                "available": True, "earned_at": "2026-10-31T00:00:00Z",
                "badges": {"starstruck": {"tier": 0, "value": 2, "repo": "<x&y>"}}
            }), encoding="utf-8")
            subprocess.run([sys.executable, str(root / "scripts" / "render_achievements.py")], check=True)
            svg = (root / "assets" / "achievements.svg").read_text(encoding="utf-8")
            ET.fromstring(svg)
            self.assertIn("&lt;x&amp;y&gt;", svg)
            self.assertIn("? / 2 merged PRs", svg)


if __name__ == "__main__":
    unittest.main()
