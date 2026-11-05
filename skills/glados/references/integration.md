# Installation, integration and migration

## Prerequisites and installation

Use Python 3.11+, PyYAML and jsonschema from the host's declared environment. `pyproject.toml`
records dependencies, not permission to install them imperatively. Missing dependencies must follow
WF-09 through nix-systems, with no switch. Only TTS-enabled installation requires `glados-say` on
PATH.

From the skill directory, run `python scripts/install.py`. Always confirm the amgmt path,
global/agent enablement, name, personality path, TTS, maximum length, and every project's name,
path, privacy, enablement and completion permission. The installer uses a serialized YAML document
as the HBS template's raw `configuration` value. This avoids hand-built YAML quoting or a template
engine dependency. Schema defaults do not modify input.

All values and discovery symlinks are previewed before confirmation. Enabled agents receive links to
this source under their native skills directories; conflicting existing skills are never replaced.
Keep the source directory available after installation. All values are previewed before
confirmation. Existing phrases are validated against the proposed configuration and preserved.
Existing configuration receives a dated backup before replacement. Rejected/invalid input writes
nothing. Project removal or privacy changes that invalidate existing phrases require a separate
reviewed catalog migration; installation does not discard phrases.

## Integration contract

| Runtime                    | Request adapter  | Completion adapter | Activation status                                       |
| -------------------------- | ---------------- | ------------------ | ------------------------------------------------------- |
| Codex                      | UserPromptSubmit | Stop               | Fixture tested; runtime/trust verification required     |
| Claude Code                | UserPromptSubmit | Stop               | Fixture tested; runtime verification required           |
| Hermes                     | pre_llm_call     | post_llm_call      | Fixture tested; installed-version verification required |
| Gemini, OpenClaw, ZeroClaw | None             | None               | Inventory only; no integration installed                |

The request adapter returns a context reminder for the executing agent to renew; it does not
generate phrases. Completion ignores response text and chooses only validated catalog phrases.
Hermes uses shell hooks, not gateway-only handlers. Missing CWD/session fields prevent playback. Do
not substitute a default session.

After confirming local event payloads and existing voice authorization, use:

```sh
python scripts/integrate.py --agent codex
python scripts/integrate.py --agent codex --remove
```

The registration preview requires explicit confirmation that lifecycle support was verified and
legacy speakers were disabled. Unrelated hooks survive repeated registration and removal. Ownership
manifests and backups remain local. Re-run registration if the interpreter or skill location
changes. Codex hook trust must be reviewed through its native UI; never manufacture trust records.

References: [Claude Code hooks](https://code.claude.com/docs/en/hooks),
[Hermes hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks),
[OpenAI lifecycle packaging and trust](https://developers.openai.com/plugins/build/plugins). The
generic Codex hooks documentation URL returned 404 during planning; exact installed Codex contracts
remain a deployment acceptance gate.

See [the compatibility evidence](inventory.md) for the inspected host snapshot.

## Ownership migration and rollback

Before cutover, inventory every declared Nix host and installed agent. Record prepared, published,
installed and lifecycle-tested state separately. Current local evidence includes Codex hooks,
Hermes/glados-tts declarations on kanagawa, Claude/Gemini declarations on outer-heaven, and ZeroClaw
on aperture-science. Remote execution is unverified; these are not claims of remote activation.

The installed obsidian-journal under amgmt has newer scoped renewal code than the standalone
Projects checkout. Compare their revisions before changing the journal source. Back up its
configuration, catalog and affected agent settings.

1. Keep the existing speaker enabled while validating this skill with stubbed playback. Inventory
   journal `glados.py` callers, Lua synchronization/publication, legacy TTS/plugin hooks, wiki
   events and the Nix hook installer.
2. Translate only reviewed, eligible phrases to this catalog's schema. Map legacy success events to
   completion and paths to configured project names. Reject private/unknown scope, duplicates or
   oversized phrases. Use the existing catalog as evidence, not authorization to broaden scope.
3. In the source repositories, remove journal phrase generation and direct speech calls, preserving
   journal records and maintenance. Delegate eligible completed operations to this helper only after
   real call sites are verified. Do not leave old and new completion triggers active together.
4. Remove only legacy GLaDOS hooks identified in the backup; update the Nix installer declaration so
   activation cannot restore them. Keep `glados-say` as the playback engine. Register the new
   adapter and test a fresh trusted session.
5. Publish authorized source changes and evaluate affected Nix hosts without a switch. Report remote
   deployment as pending until actually verified.

Rollback removes this skill's owned integrations and restores the backed-up legacy
configuration/catalog and source revisions. Never restore an entire agent settings backup over
unrelated subsequent changes; merge only owned entries.

Synchronization uses ordinary reviewed Git merges. Local locks do not coordinate separate clones.
Stable project/date/slot IDs expose conflicting same-day renewals; stop and resolve conflicts while
preserving both copies. Do not use the legacy merge routine's automatic deletion behavior for the
new catalog envelope.

## Acceptance

Run `python -m unittest discover -s tests -v` from the repository root in the declared Python
environment. Stub audio in automation. Claim automatic support only after observing first-request
renewal, same-day suppression and authorized completion playback on that exact runtime. Perform
audible testing only with voice authorization and matching journal scope.
