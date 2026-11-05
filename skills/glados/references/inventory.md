# Compatibility evidence — 2026-11-04

| Host                 | Prepared state                                              | Installed state                                                                           | Lifecycle state                                                    |
| -------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| kanagawa             | Standalone skill and Nix runtime                            | amgmt configuration/catalog and six discovery links; Codex/Claude/Hermes hooks registered | Direct adapter smoke tests; native trust and new sessions required |
| outer-heaven         | Shared amgmt sources and Darwin Nix declaration             | Remote update not performed; SSH rejected the available key                               | Unverified                                                         |
| aperture-science     | Shared sources and Linux Nix declaration                    | Remote update not performed; hostname did not resolve                                     | Unverified                                                         |
| Other declared hosts | Host declarations were searched; no new voice authorization | No remote installation performed                                                          | Unverified                                                         |

The configured roots are `~/Projects` and `~/.vaults`. Only Codex has `tts_enable: true`; all
configured runtimes can renew phrases. Codex and Hermes resolve on the active host's PATH. Claude
has existing settings, but its CLI did not resolve. Gemini, OpenClaw and ZeroClaw are
discoverable/manual integrations; no native automatic-hook support is claimed for them.

## Ownership after local cutover

| Operation                                  | Owner                                                         |
| ------------------------------------------ | ------------------------------------------------------------- |
| Journal maintenance                        | Existing obsidian-journal Lua workflow, now silent            |
| Phrase generation                          | Executing agent following the standalone glados skill         |
| Catalog validation, selection and throttle | Standalone glados helper                                      |
| Synthesis and playback                     | Nix-provided glados-say                                       |
| Lifecycle configuration                    | Standalone skill registrar; Nix restores its portable command |

Four Codex and five Claude legacy handlers were retired. Unrelated handlers, including Claude
journal recording, were preserved. Legacy plugin hooks and Gemini response narration were retired.
Old catalogs and affected settings have local backups under `~/.local/state/glados`; no backup
credentials are published. The standalone journal checkout retains its older layout and user-edited
weekly/monthly templates; only voice ownership changed there.

Publication and installation are distinct. Consult Git commit status for source publication; no
system switch or remote deployment occurred. See [integration.md](integration.md) for restart,
trust, migration and rollback details.
