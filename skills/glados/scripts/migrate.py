#!/usr/bin/env python3
"""Prepare or apply a reviewed legacy journal catalog migration; never activate voice."""

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import yaml
from glados import atomic, catalog_at, config_at, read, state_dir, validate, validate_config


def convert(records, config):
    """Keep eligible completion phrases; leave excluded records in the legacy backup."""
    roots = {str(Path(p["path"]).expanduser().resolve()): p for p in config["projects"]}
    result, ids, texts = [], set(), set()
    for old in records:
        scope = old.get("project", {})
        path = scope.get("path") if isinstance(scope, dict) else None
        candidate = Path(path).expanduser().resolve() if isinstance(path, str) else None
        matching = [
            (root, item)
            for root, item in roots.items()
            if candidate is not None and candidate.is_relative_to(root)
        ]
        project = max(matching, key=lambda pair: len(Path(pair[0]).parts))[1] if matching else None
        text = old.get("phrase")
        if (
            not project
            or project["private"]
            or not project["enable"]
            or old.get("event") not in ("success", "completion")
            or not isinstance(text, str)
            or not 0 < len(text) <= config["tts"]["max_length"]
            or text != " ".join(text.split())
            or text in texts
        ):
            continue
        identifier = hashlib.sha256(
            (project["name"] + ":legacy:" + str(old.get("id", text))).encode()
        ).hexdigest()
        if identifier in ids:
            continue
        record = {key: old[key] for key in ("phrase", "created_at", "updated_at")}
        record.update(
            id=identifier,
            enable=old.get("enable") is True,
            project=project["name"],
            event="completion",
            topic=old.get("topic") or "maintenance",
        )
        validate("phrases", {"phrases": [record], "renewed": {}})
        result.append(record)
        ids.add(identifier)
        texts.add(text)
    return {"phrases": result, "renewed": {}}


def migrate(vault, journal, config, apply=False):
    vault = Path(vault).expanduser().resolve(strict=True)
    if not vault.is_relative_to((Path.home() / ".vaults").resolve()):
        raise ValueError("amgmt must be beneath ~/.vaults")
    validate_config(config)
    source = Path(journal).expanduser().resolve(strict=True) / ".glados/phrases.yaml"
    if not source.is_relative_to((Path.home() / ".vaults").resolve()):
        raise ValueError("Legacy journal must be beneath ~/.vaults")
    records = read(source) if source.exists() else []
    if not isinstance(records, list):
        raise TypeError("Legacy catalog must contain an array")
    converted = convert(records, config)
    destination = vault / ".glados/phrases.yaml"
    config_path = vault / ".glados.config.yaml"
    print(
        json.dumps(
            {
                "legacy_records": len(records),
                "eligible_records": len(converted["phrases"]),
                "destination": str(destination),
                "apply": apply,
            }
        )
    )
    if not apply:
        return converted
    if config_path.exists() or destination.exists():
        existing_vault, existing_config = config_at(vault)
        catalog_at(existing_vault, existing_config)
        if existing_config != config:
            raise ValueError("Existing configuration differs; use interactive reinstallation")
        return catalog_at(vault, existing_config)
    backup = state_dir(vault) / ("migration-" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
    backup.mkdir(parents=True)
    if source.exists():
        shutil.copy2(source, backup / "legacy-phrases.yaml")
    atomic(destination, yaml.safe_dump(converted, sort_keys=False))
    atomic(config_path, yaml.safe_dump(config, sort_keys=False))
    catalog_at(*config_at(vault))
    return converted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--config", required=True, help="Previously reviewed configuration YAML")
    parser.add_argument(
        "--apply", action="store_true", help="Apply the configuration already confirmed by the user"
    )
    args = parser.parse_args()
    migrate(args.vault, args.journal, read(args.config), args.apply)
