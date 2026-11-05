#!/usr/bin/env python3
"""Interactive configuration installation. Does not enable lifecycle hooks."""

import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml
from glados import AGENTS, SKILL, ValidationError, atomic, catalog_at, config_at, read, validate


def ask(label, default):
    answer = input(f"{label} [{default}]: ").strip()
    return answer or str(default)


def boolean(label, default=False):
    answer = ask(label + " (yes/no)", "yes" if default else "no")
    if answer not in ("yes", "no"):
        raise ValueError("Answer yes or no")
    return answer == "yes"


def install():
    vault = (
        Path(ask("Existing amgmt directory", Path.home() / ".vaults/amgmt"))
        .expanduser()
        .resolve(strict=True)
    )
    if not vault.is_relative_to((Path.home() / ".vaults").resolve()):
        raise ValueError("amgmt must be beneath ~/.vaults")
    path = vault / ".glados.config.yaml"
    previous = validate("config", read(path)) if path.exists() else {}
    config = {"enable": boolean("Enable GLaDOS", previous.get("enable", False)), "agents": {}}
    for agent in AGENTS:
        config["agents"][agent] = {
            "enable": boolean(
                "Enable " + agent + " renewal",
                previous.get("agents", {}).get(agent, {}).get("enable", False),
            )
        }
    config["name"] = ask("Name", previous.get("name", "GLaDOS"))
    personality = ask("Personality document (none to omit)", previous.get("personality", "none"))
    if personality != "none":
        if not Path(personality).expanduser().is_file():
            raise ValueError("Personality document is unavailable")
        config["personality"] = personality
    tts = previous.get("tts", {})
    config["tts"] = {
        "enable": boolean("Enable authorized completion voice", tts.get("enable", False)),
        "max_length": int(ask("Maximum phrase length", tts.get("max_length", 100))),
        "hooks": {},
    }
    if config["tts"]["enable"] and not shutil.which("glados-say"):
        raise ValueError("Declare glados-say through Nix before enabling voice")
    old_projects = previous.get("projects", [])
    count = int(ask("Number of projects", len(old_projects)))
    if count < 0:
        raise ValueError("Project count cannot be negative")
    config["projects"] = []
    for index in range(count):
        old = old_projects[index] if index < len(old_projects) else {}
        name = ask("Project name", old.get("name", f"project-{index + 1}"))
        root = ask("Project path", old.get("path", "~/Projects/" + name))
        if not Path(root).expanduser().is_absolute():
            raise ValueError("Project paths must be absolute or home-relative")
        project = {
            "name": name,
            "path": root,
            "enable": boolean("Enable project", old.get("enable", False)),
            "private": boolean("Private project (no content inspection)", old.get("private", True)),
        }
        config["projects"].append(project)
        config["tts"]["hooks"][name] = {
            "completion": boolean(
                "Permit completion voice for " + name,
                tts.get("hooks", {}).get(name, {}).get("completion", False),
            )
        }
    validate("config", config)
    if len({p["name"] for p in config["projects"]}) != count:
        raise ValueError("Project names must be unique")
    # Validate preserved phrases against proposed configuration before any write.
    catalog_at(vault, config)
    encoded = yaml.safe_dump(config, sort_keys=False)
    rendered = (
        (SKILL / "templates/config.yaml.hbs")
        .read_text()
        .replace("{{{configuration}}}", encoded.rstrip())
    )
    validate("config", yaml.safe_load(rendered))
    destinations = {
        "codex": ".agents/skills/glados",
        "claude-code": ".claude/skills/glados",
        "hermes": ".hermes/skills/glados",
    }
    links = [
        Path.home() / destinations[agent] for agent in AGENTS if config["agents"][agent]["enable"]
    ]
    for link in links:
        if (link.exists() or link.is_symlink()) and link.resolve() != SKILL:
            raise FileExistsError("An unrelated skill already exists at the selected destination")
    print(rendered)
    print("Skill discovery links: " + ", ".join(str(link) for link in links))
    if not boolean("Write this exact configuration"):
        return
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".backup-" + stamp))
    catalog = vault / ".glados/phrases.yaml"
    if not catalog.exists():
        atomic(catalog, "phrases: []\nrenewed: {}\n")
    atomic(path, rendered)
    config_at(vault)
    for link in links:
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink():
            link.symlink_to(SKILL, target_is_directory=True)
    print(
        "Configuration installed. Lifecycle integrations remain unregistered; follow references/integration.md."
    )


if __name__ == "__main__":
    try:
        install()
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as error:
        print(
            f"GLaDOS installation failed: {type(error).__name__}; existing files were preserved unless a confirmed write completed.",
            file=sys.stderr,
        )
        sys.exit(1)
