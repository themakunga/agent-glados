#!/usr/bin/env python3
"""Register/remove skill-owned hooks after local runtime verification."""

import argparse
import json
import shlex
import sys
from pathlib import Path

import yaml
from glados import AGENTS, SKILL, atomic, config_at, lock, state_dir


def integrate(vault, agent, remove=False):
    vault, config = config_at(vault)
    script = SKILL / "scripts/glados.py"
    command = shlex.join(
        [sys.executable, str(script), "--vault", str(vault), "--agent", agent, "hook"]
    )
    if agent == "hermes":
        path = Path.home() / ".hermes/config.yaml"
        events = ("pre_llm_call", "post_llm_call")
    else:
        path = Path.home() / (".codex/hooks.json" if agent == "codex" else ".claude/settings.json")
        events = ("UserPromptSubmit", "Stop")
    path = path.resolve()
    if remove and not (state_dir(vault) / f"integration-{agent}.json").exists():
        return
    manifest = state_dir(vault) / f"integration-{agent}.json"
    with lock(state_dir(vault) / "integration.lock"):
        data = (
            (
                yaml.safe_load(path.read_text())
                if agent == "hermes"
                else json.loads(path.read_text())
            )
            if path.exists()
            else {}
        )
        if not isinstance(data, dict):
            raise TypeError("Agent configuration must be a mapping")
        entries = manifest.exists() and json.loads(manifest.read_text())
        if entries:
            if entries["path"] != str(path):
                raise ValueError("Agent configuration moved; review integration manifest")
            for event, entry in entries["entries"].items():
                groups = data.get("hooks", {}).get(event, [])
                if entry in groups:
                    groups.remove(entry)
        if not remove and "glados-hook" in json.dumps(data.get("hooks", {})):
            raise ValueError("Legacy GLaDOS hook still exists; migrate it before registration")
        added = {}
        if not remove:
            if not config["agents"].get(agent, {}).get("enable"):
                raise ValueError("Agent is disabled")
            for event in events:
                entry = (
                    {"command": command}
                    if agent == "hermes"
                    else {
                        "hooks": [
                            {
                                "type": "command",
                                "command": command,
                                "timeout": 15 if event == "UserPromptSubmit" else 300,
                            }
                        ]
                    }
                )
                groups = data.setdefault("hooks", {}).setdefault(event, [])
                # Exact pre-existing entries are not claimed by this installer.
                if entry not in groups:
                    groups.append(entry)
                    added[event] = entry
        content = (
            yaml.safe_dump(data, sort_keys=False)
            if agent == "hermes"
            else json.dumps(data, indent=2) + "\n"
        )
        if not remove:
            print(json.dumps({"path": str(path), "owned_hooks": added}, indent=2))
            if (
                input(
                    "Runtime lifecycle verified and legacy speakers disabled; register these hooks? (yes/no): "
                )
                != "yes"
            ):
                return
        if path.exists():
            backup = path.with_name(path.name + ".before-glados-skill")
            if not backup.exists():
                atomic(backup, path.read_text())
        # Write ownership first so an interrupted settings write is recoverable.
        if not remove:
            atomic(manifest, json.dumps({"path": str(path), "entries": added}))
        atomic(path, content)
        if remove:
            manifest.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(Path.home() / ".vaults/amgmt"))
    parser.add_argument("--agent", choices=AGENTS, required=True)
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    integrate(args.vault, args.agent, args.remove)
