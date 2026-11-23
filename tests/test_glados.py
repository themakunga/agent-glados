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
import glados as g  # noqa: E402
import install  # noqa: E402
import integrate  # noqa: E402
import migrate  # noqa: E402


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
        self.config["agents"]["codex"]["tts_enable"] = True
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
        self.config["tts"]["hooks"]["example"]["input"] = True
        self.save()
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
        installed = g.read(self.vault / ".glados.config.yaml")
        self.assertTrue(installed["tts"]["hooks"]["example"]["input"])

    def test_permission_request_is_registered(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            integrate.integrate(self.vault, "codex", confirmed=True)
        hooks = json.loads((self.home / ".codex/hooks.json").read_text())["hooks"]
        self.assertIn("PermissionRequest", hooks)
        self.assertEqual(hooks["PermissionRequest"][0]["hooks"][0]["timeout"], 300)
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], g.INPUT_TOOLS)

    def test_alert_banks_remain_available_after_completion_renewal(self):
        pools = g.alerts_at(self.vault)
        for pool in pools.values():
            self.assertGreaterEqual(len(set(pool)), 10)
            self.assertTrue(all(len(text) <= self.config["tts"]["max_length"] for text in pool))
        g.renew_alerts(self.vault, pools)
        path = self.vault / ".glados/alerts.yaml"
        before = path.read_bytes()
        renew_once(self.vault)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(g.alerts_at(self.vault), pools)

    def test_invalid_alert_updates_preserve_both_banks(self):
        pools = g.alerts_at(self.vault)
        g.renew_alerts(self.vault, pools)
        path = self.vault / ".glados/alerts.yaml"
        before = path.read_bytes()
        for replacement in (
            pools["permission"][:9],
            [pools["permission"][0]] * 10,
            ["This  contains duplicate spaces."] + pools["permission"][1:],
            ["This contains a\x00control character."] + pools["permission"][1:],
            ["x" * 101] + pools["permission"][1:],
        ):
            with (
                self.subTest(replacement=replacement),
                self.assertRaises((ValueError, g.ValidationError)),
            ):
                g.renew_alerts(self.vault, dict(pools, permission=replacement))
            self.assertEqual(path.read_bytes(), before)
        path.write_text(g.yaml.safe_dump(dict(pools, input=pools["input"][:9])))
        with self.assertRaises(g.ValidationError):
            g.due(self.vault, self.config, "codex")

    def test_alerts_rotate_without_using_completion_throttle(self):
        self.config["tts"]["enable"] = True
        self.config["tts"]["hooks"]["example"].update(permission=True, input=True)
        pools = g.alerts_at(self.vault)
        with (
            patch.object(g.shutil, "which", return_value="glados-say"),
            patch.object(g.random, "choice", side_effect=lambda pool: pool[0]),
            patch.object(g.subprocess, "run") as run,
        ):
            for event in ("permission", "input"):
                for _ in range(3):
                    self.assertTrue(
                        g.speak(
                            self.vault,
                            self.config,
                            "codex",
                            str(self.project),
                            "session",
                            event=event,
                        )
                    )
                spoken = [call.args[0][1] for call in run.call_args_list[-3:]]
                self.assertTrue(all(text in pools[event] for text in spoken))
                self.assertNotEqual(spoken[0], spoken[1])
                self.assertNotEqual(spoken[1], spoken[2])
                self.assertTrue(
                    g.speak(
                        self.vault,
                        self.config,
                        "codex",
                        str(self.project),
                        "new-session",
                        event=event,
                    )
                )
                self.assertNotEqual(spoken[-1], run.call_args.args[0][1])
            self.assertEqual(run.call_count, 8)
        self.assertFalse(list(g.state_dir(self.vault).glob("spoken-*")))

    def test_input_hook_is_scoped_and_never_reads_the_question(self):
        self.config["tts"]["enable"] = True
        settings = self.config["tts"]["hooks"]["example"]
        settings["input"] = True
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "functions.request_user_input_async",
            "tool_input": {"questions": "private-question-payload"},
            "cwd": str(self.project),
            "session_id": "session",
        }
        with (
            patch.object(g.shutil, "which", return_value="glados-say"),
            patch.object(g.subprocess, "run") as run,
        ):
            for name in (
                "request_user_input",
                "request_user_input_async",
                "functions.request_user_input_async",
            ):
                self.assertEqual(
                    g.hook(self.vault, self.config, "codex", dict(payload, tool_name=name)), {}
                )
            self.assertEqual(run.call_count, 3)
            self.assertTrue(
                all("private-question-payload" not in str(call) for call in run.call_args_list)
            )
            for name in ("Bash", "exec_command", "not_request_user_input_helper", None):
                g.hook(self.vault, self.config, "codex", dict(payload, tool_name=name))
            settings["input"] = False
            g.hook(self.vault, self.config, "codex", payload)
            settings["input"] = True
            self.config["agents"]["codex"]["tts_enable"] = False
            g.hook(self.vault, self.config, "codex", payload)
            self.config["agents"]["codex"]["tts_enable"] = True
            g.hook(self.vault, self.config, "codex", dict(payload, cwd=str(self.home)))
            g.hook(self.vault, self.config, "codex", dict(payload, session_id=None))
            g.hook(self.vault, self.config, "claude-code", payload)
            self.assertEqual(run.call_count, 3)

    def test_permission_request_speaks_without_an_approval_decision(self):
        self.config["tts"]["enable"] = True
        self.config["tts"]["hooks"]["example"]["permission"] = True
        payload = {
            "hook_event_name": "PermissionRequest",
            "cwd": str(self.project),
            "session_id": "session",
            "turn_id": "turn",
            "tool_name": "shell",
            "tool_input": {"command": "echo test"},
        }
        with (
            patch.object(g.shutil, "which", return_value="glados-say"),
            patch.object(g.subprocess, "run") as run,
        ):
            self.assertEqual(g.hook(self.vault, self.config, "codex", payload), {})
            self.assertEqual(run.call_count, 1)
            self.assertIn("approval", run.call_args.args[0][1].lower())

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
            patch.object(g.subprocess, "run") as run,
        ):
            self.config["tts"]["enable"] = True
            self.config["agents"]["codex"]["tts_enable"] = False
            g.speak(self.vault, self.config, "codex", str(self.project), "test")
            run.assert_not_called()

    def test_permission_voice_is_independent_and_stays_scoped(self):
        renew_once(self.vault)
        self.config["tts"]["enable"] = True
        settings = self.config["tts"]["hooks"]["example"]
        settings.update(completion=True, permission=True)
        g.validate("config", self.config)
        payload = {
            "hook_event_name": "PermissionRequest",
            "cwd": str(self.project),
            "session_id": "session",
        }
        with (
            patch.object(g.shutil, "which", return_value="glados-say"),
            patch.object(g.subprocess, "run") as run,
            patch.object(g.time, "time", return_value=1000),
        ):
            self.assertTrue(g.speak(self.vault, self.config, "codex", str(self.project), "session"))
            for _ in range(2):
                self.assertEqual(g.hook(self.vault, self.config, "codex", payload), {})
            self.assertFalse(
                g.speak(self.vault, self.config, "codex", str(self.project), "session")
            )
            self.assertEqual(run.call_count, 3)
            settings["permission"] = False
            g.hook(self.vault, self.config, "codex", payload)
            settings["permission"] = True
            g.hook(self.vault, self.config, "codex", dict(payload, cwd=str(self.home)))
            self.config["agents"]["codex"]["tts_enable"] = False
            g.hook(self.vault, self.config, "codex", payload)
            self.config["agents"]["codex"]["tts_enable"] = True
            self.config["tts"]["max_length"] = 5
            g.hook(self.vault, self.config, "codex", payload)
            self.assertEqual(run.call_count, 3)

    def test_migration_filters_and_preserves_legacy(self):
        legacy = self.home / ".vaults/journal"
        legacy.mkdir()
        example = g.read(g.SKILL / "templates/phrases.example.yaml")["phrases"][0]
        example["project"] = {"path": str(self.project), "is_project": True}
        example["event"] = "success"
        records = [
            example,
            dict(example, id="unscoped", project={}),
            dict(example, id="error", event="failure"),
        ]
        source = legacy / ".glados/phrases.yaml"
        g.atomic(source, g.yaml.safe_dump(records))
        before = source.read_bytes()
        (self.vault / ".glados.config.yaml").unlink()
        result = migrate.migrate(self.vault, legacy, self.config, apply=True)
        self.assertEqual(len(result["phrases"]), 1)
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(migrate.migrate(self.vault, legacy, self.config, apply=True), result)
        private = g.yaml.safe_load(g.yaml.safe_dump(self.config))
        private["projects"][0]["private"] = True
        self.assertEqual(migrate.convert(records, private)["phrases"], [])

    def test_agent_voice_authorization_is_independent(self):
        renew_once(self.vault)
        self.config["agents"]["hermes"]["enable"] = True
        self.config["tts"]["enable"] = True
        self.config["tts"]["hooks"]["example"]["completion"] = True
        with patch.object(g.subprocess, "run") as run:
            self.assertFalse(
                g.speak(self.vault, self.config, "hermes", str(self.project), "session")
            )
            run.assert_not_called()
        self.assertEqual(g.due(self.vault, self.config, "hermes"), [])

    def test_examples_and_formats(self):
        g.validate("config", self.config)
        catalog = g.read(g.SKILL / "templates/phrases.example.yaml")
        g.validate("phrases", catalog)
        for invalid in ("yesterday", "2026-11-04T12:00:00", "20261104T120000+0000"):
            catalog["phrases"][0]["created_at"] = invalid
            with self.assertRaises(g.ValidationError):
                g.validate("phrases", catalog)
        with self.assertRaises(TypeError):
            g.hook(self.vault, self.config, "codex", [])

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

    def test_completion_resumes_after_thirty_seconds(self):
        renew_once(self.vault)
        self.config["tts"]["enable"] = True
        self.config["tts"]["hooks"]["example"]["completion"] = True
        with (
            patch.object(g.shutil, "which", return_value="glados-say"),
            patch.object(g.subprocess, "run") as run,
            patch.object(g.time, "time", return_value=1000) as clock,
        ):
            self.assertTrue(g.speak(self.vault, self.config, "codex", str(self.project), "s"))
            clock.return_value = 1029.999
            self.assertFalse(g.speak(self.vault, self.config, "codex", str(self.project), "s"))
            clock.return_value = 1030
            self.assertTrue(g.speak(self.vault, self.config, "codex", str(self.project), "s"))
            self.assertEqual(run.call_count, 2)

    def test_scope_throttle_and_private_child(self):
        renew_once(self.vault)
        self.config["tts"]["enable"] = True
        self.config["tts"]["hooks"]["example"]["completion"] = True
        with (
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

    def test_legacy_migration_preserves_mixed_groups(self):
        path = self.home / ".codex/hooks.json"
        legacy = {"type": "command", "command": '"$HOME/.local/bin/glados-hook"'}
        unrelated = {"type": "command", "command": "unrelated"}
        g.atomic(path, json.dumps({"hooks": {"Stop": [{"hooks": [legacy, unrelated]}]}}))
        with patch("sys.stdout", new_callable=io.StringIO):
            integrate.integrate(self.vault, "codex", confirmed=True, migrate_legacy=True)
        handlers = [
            h for group in json.loads(path.read_text())["hooks"]["Stop"] for h in group["hooks"]
        ]
        self.assertIn(unrelated, handlers)
        self.assertNotIn(legacy, handlers)
        self.assertTrue((g.state_dir(self.vault) / "settings-codex.before-glados-skill").is_file())

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
