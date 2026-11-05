#!/usr/bin/env python3
"""Register/remove skill-owned hooks after local runtime verification."""

import argparse
import json
from pathlib import Path

import yaml
from glados import atomic, config_at, lock, state_dir


def integrate(vault, agent, remove=False, confirmed=False, migrate_legacy=False):
    if agent not in ("codex", "claude-code", "hermes"):
        raise ValueError("No verified automatic lifecycle adapter for this agent")
    vault, config = config_at(vault)
    command = f'"$HOME/.local/bin/glados-agent" --agent {agent} hook'
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
        legacy = '"$HOME/.local/bin/glados-hook"'
        legacy_count = 0
        if migrate_legacy:
            for groups in data.get("hooks", {}).values():
                for group in list(groups):
                    handlers = group.get("hooks", [])
                    kept = [handler for handler in handlers if handler.get("command") != legacy]
                    legacy_count += len(handlers) - len(kept)
                    if kept != handlers:
                        if kept:
                            group["hooks"] = kept
                        else:
                            groups.remove(group)
        if not remove and "glados-hook" in json.dumps(data.get("hooks", {})):
            raise ValueError("Unrecognized legacy GLaDOS hook; review before registration")
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
            print(
                json.dumps(
                    {
                        "path": str(path),
                        "owned_hooks": added,
                        "retired_legacy_handlers": legacy_count,
                    },
                    indent=2,
                )
            )
            if (
                not confirmed
                and input(
                    "Register these hooks (native trust and session restart remain required)? (yes/no): "
                )
                != "yes"
            ):
                return
        if path.exists():
            backup = state_dir(vault) / f"settings-{agent}.before-glados-skill"
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
    parser.add_argument("--agent", choices=("codex", "claude-code", "hermes"), required=True)
    parser.add_argument("--remove", action="store_true")
    parser.add_argument(
        "--apply", action="store_true", help="Register the reviewed hooks without another prompt"
    )
    parser.add_argument(
        "--migrate-legacy", action="store_true", help="Retire only the exact known legacy command"
    )
    args = parser.parse_args()
    integrate(args.vault, args.agent, args.remove, args.apply, args.migrate_legacy)
