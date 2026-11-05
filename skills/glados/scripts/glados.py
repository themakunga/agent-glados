#!/usr/bin/env python3
"""Validated GLaDOS catalog, request hooks and completion playback."""

import argparse
import fcntl
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

SKILL = Path(__file__).resolve().parents[1]
AGENTS = ("codex", "claude-code", "hermes")


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys rather than silently discarding configuration."""


def mapping(loader, node):
    result = {}
    for key, value in node.value:
        key = loader.construct_object(key)
        if key in result:
            raise ValueError("Duplicate YAML key")
        result[key] = loader.construct_object(value)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def read(path):
    return yaml.load(Path(path).read_text(), Loader=UniqueLoader)


def validate(kind, value):
    schema = json.loads((SKILL / "schemas" / f"{kind}.json").read_text())
    checker = FormatChecker()

    @checker.checks("date-time", raises=(ValueError, TypeError))
    def timestamp(text):
        return (
            isinstance(text, str)
            and "T" in text
            and datetime.fromisoformat(text).tzinfo is not None
        )

    @checker.checks("date", raises=(ValueError, TypeError))
    def day(text):
        return isinstance(text, str) and date.fromisoformat(text).isoformat() == text

    Draft202012Validator(schema, format_checker=checker).validate(value)
    return value


def config_at(vault):
    vault = Path(vault).expanduser().resolve(strict=True)
    if not vault.is_relative_to((Path.home() / ".vaults").resolve()):
        raise ValueError("The amgmt directory must be beneath ~/.vaults")
    config = validate("config", read(vault / ".glados.config.yaml"))
    if any(not Path(p["path"]).expanduser().is_absolute() for p in config["projects"]):
        raise ValueError("Project paths must be absolute or home-relative")
    names = [p["name"] for p in config["projects"]]
    if len(names) != len(set(names)):
        raise ValueError("Project names must be unique")
    if set(config["tts"]["hooks"]) - set(names):
        raise ValueError("Unknown project in event settings")
    return vault, config


def catalog_at(vault, config):
    path = vault / ".glados/phrases.yaml"
    data = validate("phrases", read(path)) if path.exists() else {"phrases": [], "renewed": {}}
    names = {p["name"] for p in config["projects"]}
    ids = [p["id"] for p in data["phrases"]]
    if len(ids) != len(set(ids)) or set(data["renewed"]) - names:
        raise ValueError("Duplicate phrase IDs or unknown renewal project")
    for phrase in data["phrases"]:
        if phrase["project"] not in names or len(phrase["phrase"]) > config["tts"]["max_length"]:
            raise ValueError("Unknown phrase project or excessive length")
        if phrase["phrase"] != " ".join(phrase["phrase"].split()):
            raise ValueError("Phrases must be single normalized lines")
        if next(p for p in config["projects"] if p["name"] == phrase["project"])["private"]:
            raise ValueError("Private projects cannot have synchronized phrases")
    return data


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def state_dir(vault):
    key = hashlib.sha256(str(vault).encode()).hexdigest()[:16]
    return Path.home() / ".local/state/glados" / key


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def projects(config, agent):
    if not config["enable"] or not config["agents"].get(agent, {}).get("enable", False):
        return []
    available = []
    for project in config["projects"]:
        root = Path(project["path"]).expanduser().resolve()
        if project["enable"] and not project["private"] and root.is_dir():
            available.append((project, root))
    return available


def due(vault, config, agent):
    data = catalog_at(vault, config)
    return [
        p["name"]
        for p, _ in projects(config, agent)
        if data["renewed"].get(p["name"]) != date.today().isoformat()
    ]


def renew(vault, agent, name, proposals):
    with lock(state_dir(vault) / "catalog.lock"):
        vault, config = config_at(vault)
        if name not in [p["name"] for p, _ in projects(config, agent)]:
            raise ValueError("Project is disabled, private or unavailable")
        data = catalog_at(vault, config)
        today = date.today()
        if data["renewed"].get(name) == today.isoformat():
            return False
        if not isinstance(proposals, list) or len(proposals) not in (0, 2):
            raise ValueError(
                "Supply two phrases, or an empty list after inspecting an empty project"
            )
        texts = []
        for item in proposals:
            if not isinstance(item, dict) or set(item) != {"phrase", "topic"}:
                raise ValueError("Each proposal requires only phrase and topic")
            texts.append(item["phrase"])
        if any(not isinstance(t, str) for t in texts) or len(set(texts)) != len(texts):
            raise ValueError("Phrases must be distinct strings")
        if set(texts) & {p["phrase"] for p in data["phrases"]}:
            raise ValueError("Phrase text already exists")
        cutoff = today - timedelta(days=7)
        data["phrases"] = [
            p
            for p in data["phrases"]
            if p["project"] != name
            or datetime.fromisoformat(p["created_at"]).astimezone().date() > cutoff
        ]
        topics = {p["topic"] for p in proposals}
        for record in data["phrases"]:
            if record["project"] == name and record["topic"] not in topics:
                record["enable"] = False
                record["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        now = datetime.now(UTC).isoformat(timespec="seconds")
        for slot, item in enumerate(proposals):
            identifier = hashlib.sha256(f"{name}:{today}:{slot}".encode()).hexdigest()
            data["phrases"].append(
                dict(
                    item,
                    id=identifier,
                    project=name,
                    event="completion",
                    enable=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        data["renewed"][name] = today.isoformat()
        validate("phrases", data)
        # Reuse the complete cross-file validation before replacing the catalog.
        for record in data["phrases"]:
            if len(record["phrase"]) > config["tts"]["max_length"] or record["phrase"] != " ".join(
                record["phrase"].split()
            ):
                raise ValueError("Phrase exceeds configured length or contains extra whitespace")
        atomic(vault / ".glados/phrases.yaml", yaml.safe_dump(data, sort_keys=False))
        return True


def journal_allows(cwd):
    pointer = Path.home() / ".obsidian-journal-vault"
    if not pointer.is_file():
        return False
    journal = Path(pointer.read_text().strip()).expanduser().resolve(strict=True)
    if not journal.is_relative_to((Path.home() / ".vaults").resolve()):
        return False
    settings = tomllib.loads((journal / ".journal.config.toml").read_text())
    return settings.get("glados", {}).get("enable") is True and any(
        entry.get("enable") is True
        and cwd.is_relative_to(Path(entry["path"]).expanduser().resolve())
        for entry in settings.get("authorized_dirs", [])
    )


def speak(vault, config, agent, cwd, session):
    if not session or not cwd or not config["tts"]["enable"]:
        return False
    cwd = Path(cwd).resolve(strict=True)
    containing = [
        p for p in config["projects"] if cwd.is_relative_to(Path(p["path"]).expanduser().resolve())
    ]
    if any(not p["enable"] or p["private"] for p in containing):
        return False
    matches = [(p, root) for p, root in projects(config, agent) if cwd.is_relative_to(root)]
    if not matches or not journal_allows(cwd):
        return False
    project, _ = max(matches, key=lambda pair: len(pair[1].parts))
    if not config["tts"]["hooks"].get(project["name"], {}).get("completion", False):
        return False
    pool = [
        p["phrase"]
        for p in catalog_at(vault, config)["phrases"]
        if p["enable"]
        and p["event"] == "completion"
        and p["project"] == project["name"]
        and datetime.fromisoformat(p["created_at"]).astimezone().date()
        > date.today() - timedelta(days=7)
    ]
    if not pool:
        return False
    key = hashlib.sha256(f"{agent}:{session}".encode()).hexdigest()
    marker = state_dir(vault) / f"spoken-{key}.json"
    with lock(marker.with_suffix(".lock")):
        now = time.time()
        if marker.exists() and now - json.loads(marker.read_text()) < 90:
            return False
        executable = shutil.which("glados-say")
        if not executable:
            raise ValueError("glados-say is unavailable; declare it through Nix")
        subprocess.run([executable, random.choice(pool)], check=True, timeout=300)
        atomic(marker, json.dumps(time.time()))
    return True


def request(vault, config, agent):
    names = due(vault, config, agent)
    if not names:
        return ""
    return (
        f"Use the GLaDOS skill at {SKILL}. Renew these projects before completing this request: "
        + json.dumps(names)
        + ". Inspect authorized non-private context; write two short, dryly "
        "sarcastic English completion phrases per project. Do not claim unverified results. "
        "Pass proposals to glados.py renew. Empty inspected context may use []."
    )


def hook(vault, config, agent, payload):
    if not isinstance(payload, dict):
        raise TypeError("Hook input must be an object")
    event = payload.get("hook_event_name") or payload.get("event")
    if event in ("UserPromptSubmit", "pre_llm_call"):
        context = request(vault, config, agent)
        if agent == "hermes":
            return {"context": context} if context else {}
        return (
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }
            if context
            else {}
        )
    if event in ("Stop", "post_llm_call") and not payload.get("stop_hook_active"):
        speak(vault, config, agent, payload.get("cwd"), payload.get("session_id"))
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=str(Path.home() / ".vaults/amgmt"))
    parser.add_argument("--agent", choices=AGENTS, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "due", "request", "hook"):
        sub.add_parser(name)
    renewal = sub.add_parser("renew")
    renewal.add_argument("project")
    playback = sub.add_parser("speak")
    playback.add_argument("--cwd", required=True)
    playback.add_argument("--session", required=True)
    args = parser.parse_args()
    vault, config = config_at(args.vault)
    if args.command == "validate":
        catalog_at(vault, config)
        print("Configuration and catalog are valid.")
    elif args.command == "due":
        print(json.dumps(due(vault, config, args.agent)))
    elif args.command == "request":
        print(request(vault, config, args.agent))
    elif args.command == "renew":
        print(renew(vault, args.agent, args.project, json.load(sys.stdin)))
    elif args.command == "hook":
        print(json.dumps(hook(vault, config, args.agent, json.load(sys.stdin))))
    else:
        speak(vault, config, args.agent, args.cwd, args.session)


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        ValidationError,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ) as error:
        print(
            f"GLaDOS: {type(error).__name__}; check configuration, catalog and runtime prerequisites.",
            file=sys.stderr,
        )
        sys.exit(1)
