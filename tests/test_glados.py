"""Data preservation and authorization regression checks; no audible playback."""

import io
import json
import multiprocessing
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/glados/scripts"))
import glados as g
import install
import integrate


def renew_once(vault):
    return g.renew(
        Path(vault),
        "codex",
        "example",
        [
            {"phrase": "Your tests survived. How inconvenient.", "topic": "tests"},
            {"phrase": "Another configuration escaped containment.", "topic": "tests"},
        ],
    )


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.mock_home = patch.object(Path, "home", return_value=self.home)
        self.mock_home.start()
        self.vault = self.home / ".vaults/amgmt"
        self.vault.mkdir(parents=True)
        self.project = self.home / "project"
        self.project.mkdir()
        self.config = g.read(g.SKILL / "templates/config.example.yaml")
        self.config["projects"][0]["path"] = str(self.project)
        self.save()

    def tearDown(self):
        self.mock_home.stop()
        self.temp.cleanup()

    def save(self):
        g.atomic(self.vault / ".glados.config.yaml", g.yaml.safe_dump(self.config))

    def test_concurrent_local_renewal(self):
        context = multiprocessing.get_context("fork")
        with context.Pool(2) as pool:
            results = pool.map(renew_once, [str(self.vault)] * 2)
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(g.catalog_at(self.vault, self.config)["phrases"]), 2)

    def test_preserve_unavailable_host_and_expire_local(self):
        renew_once(self.vault)
        data = g.catalog_at(self.vault, self.config)
        self.config["projects"].append(
            {"name": "remote", "path": str(self.home / "missing"), "enable": True, "private": False}
        )
        remote = dict(data["phrases"][0], id="remote", project="remote")
        data["phrases"].append(remote)
        data["renewed"] = {}
        data["phrases"][0]["created_at"] = "2000-01-01T00:00:00+00:00"
        self.save()
        g.atomic(self.vault / ".glados/phrases.yaml", g.yaml.safe_dump(data))
        g.renew(self.vault, "codex", "example", [])
        kept = g.catalog_at(self.vault, self.config)["phrases"]
        self.assertIn(remote, kept)
        self.assertFalse(any(p["created_at"].startswith("2000") for p in kept))

    def test_reinstall_preserves_catalog_and_creates_backup(self):
        renew_once(self.vault)
        catalog = (self.vault / ".glados/phrases.yaml").read_bytes()
        with (
            patch.object(install, "ask", side_effect=lambda label, default: str(default)),
            patch.object(
                install,
                "boolean",
                side_effect=lambda label, default=False: (
                    True if label.startswith("Write") else default
                ),
            ),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            install.install()
        self.assertEqual((self.vault / ".glados/phrases.yaml").read_bytes(), catalog)
        self.assertEqual(len(list(self.vault.glob(".glados.config.yaml.backup-*"))), 1)

    def test_other_adapters_and_errors(self):
        for agent in ("claude-code", "hermes"):
            self.config["agents"][agent]["enable"] = True
            self.save()
            with (
                patch("builtins.input", return_value="yes"),
                patch("sys.stdout", new_callable=io.StringIO),
            ):
                integrate.integrate(self.vault, agent)
                integrate.integrate(self.vault, agent)
            integrate.integrate(self.vault, agent, remove=True)
        with patch.object(g, "speak") as speak:
            self.assertEqual(
                g.hook(self.vault, self.config, "codex", {"hook_event_name": "PreToolUse"}), {}
            )
            speak.assert_not_called()
        with (
            patch.object(g, "journal_allows", return_value=False),
            patch.object(g.subprocess, "run") as run,
        ):
            self.config["tts"]["enable"] = True
            g.speak(self.vault, self.config, "codex", str(self.project), "test")
            run.assert_not_called()

    def test_examples_and_formats(self):
        g.validate("config", self.config)
        catalog = g.read(g.SKILL / "templates/phrases.example.yaml")
        g.validate("phrases", catalog)
        catalog["phrases"][0]["created_at"] = "yesterday"
        with self.assertRaises(g.ValidationError):
            g.validate("phrases", catalog)

    def test_renew_once_and_rollover(self):
        self.assertTrue(renew_once(self.vault))
        self.assertFalse(renew_once(self.vault))
        self.assertEqual(g.due(self.vault, self.config, "codex"), [])
        data = g.catalog_at(self.vault, self.config)
        data["renewed"]["example"] = (date.today() - timedelta(days=1)).isoformat()
        g.atomic(self.vault / ".glados/phrases.yaml", g.yaml.safe_dump(data))
        self.assertEqual(g.due(self.vault, self.config, "codex"), ["example"])

    def test_invalid_proposals_preserve_catalog(self):
        g.renew(self.vault, "codex", "example", [])
        path = self.vault / ".glados/phrases.yaml"
        data = g.read(path)
        data["renewed"] = {}
        g.atomic(path, g.yaml.safe_dump(data))
        before = path.read_bytes()
        for proposals in (
            [{"phrase": "x", "topic": "test"}],
            [{"phrase": "x" * 101, "topic": "test"}, {"phrase": "second", "topic": "test"}],
        ):
            with self.assertRaises(ValueError):
                g.renew(self.vault, "codex", "example", proposals)
            self.assertEqual(path.read_bytes(), before)

    def test_failed_write_retries(self):
        with (
            patch.object(g.os, "replace", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            renew_once(self.vault)
        self.assertEqual(g.due(self.vault, self.config, "codex"), ["example"])
        self.assertTrue(renew_once(self.vault))

    def test_private_and_disabled(self):
        for key in ("private", "enable"):
            self.config["projects"][0][key] = key == "private"
            self.save()
            self.assertEqual(g.due(self.vault, self.config, "codex"), [])
        with self.assertRaises(ValueError):
            renew_once(self.vault)

    def test_unknown_project_duplicate_id(self):
        renew_once(self.vault)
        data = g.catalog_at(self.vault, self.config)
        data["phrases"].append(data["phrases"][0])
        g.atomic(self.vault / ".glados/phrases.yaml", g.yaml.safe_dump(data))
        with self.assertRaises(ValueError):
            g.catalog_at(self.vault, self.config)

    def test_scope_throttle_and_private_child(self):
        renew_once(self.vault)
        self.config["tts"]["enable"] = True
        self.config["tts"]["hooks"]["example"]["completion"] = True
        with (
            patch.object(g, "journal_allows", return_value=True),
            patch.object(g.shutil, "which", return_value="glados-say"),
            patch.object(g.subprocess, "run") as run,
        ):
            self.assertFalse(g.speak(self.vault, self.config, "codex", str(self.home), "s"))
            self.assertFalse(g.speak(self.vault, self.config, "codex", str(self.project), ""))
            self.assertTrue(g.speak(self.vault, self.config, "codex", str(self.project), "s"))
            self.assertFalse(g.speak(self.vault, self.config, "codex", str(self.project), "s"))
            self.assertEqual(run.call_count, 1)
            child = self.project / "private"
            child.mkdir()
            self.config["projects"].append(
                {"name": "secret", "path": str(child), "private": True, "enable": True}
            )
            self.assertFalse(g.speak(self.vault, self.config, "codex", str(child), "other"))
            link = self.project / "escape"
            link.symlink_to(self.home, target_is_directory=True)
            self.assertFalse(g.speak(self.vault, self.config, "codex", str(link), "other"))

    def test_empty_catalog_marker(self):
        self.assertTrue(g.renew(self.vault, "codex", "example", []))
        self.assertEqual(g.due(self.vault, self.config, "codex"), [])

    def test_duplicate_yaml_key(self):
        path = self.vault / "duplicate.yaml"
        path.write_text("enable: true\nenable: false\n")
        with self.assertRaises(ValueError):
            g.read(path)

    def test_integration_reinstall_remove(self):
        path = self.home / ".codex/hooks.json"
        unrelated = {"hooks": [{"command": "unrelated", "type": "command"}]}
        g.atomic(path, json.dumps({"hooks": {"Stop": [unrelated]}}))
        with (
            patch("builtins.input", return_value="yes"),
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            integrate.integrate(self.vault, "codex")
            integrate.integrate(self.vault, "codex")
        self.assertEqual(len(json.loads(path.read_text())["hooks"]["Stop"]), 2)
        integrate.integrate(self.vault, "codex", remove=True)
        self.assertEqual(json.loads(path.read_text())["hooks"]["Stop"], [unrelated])


if __name__ == "__main__":
    unittest.main()
