# Compatibility evidence — 2026-11-04

This is a source/declaration snapshot, not a deployment certificate.

| Host                 | Evidence                                                                                                     | New skill state                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| kanagawa             | Codex and Hermes resolve on PATH; Codex hooks exist; Nix enables Hermes and glados-tts                       | Source prepared; no installation or lifecycle execution |
| outer-heaven         | Nix declares Claude Code, Gemini and glados-tts; Darwin profile declares Codex                               | Remote installation and activation unverified           |
| aperture-science     | Nix declares Hermes, ZeroClaw service account and glados-tts                                                 | Remote installation and activation unverified           |
| Other declared hosts | motherbase, msf, steamdeck, valve, black-mesa and bootstrap declarations were included in host-source search | No new integrations prepared or deployed                |

Claude Code, Gemini, OpenClaw and ZeroClaw did not resolve on the active host's PATH. This does not
prove absence from containers or another user's environment. OpenClaw appears in historical
shared-agent policy; no current host declaration was established by this search. Other runtimes
remain inventory-only.

## Ownership

| Operation                     | Existing owner                                              | Proposed owner after verified cutover                     |
| ----------------------------- | ----------------------------------------------------------- | --------------------------------------------------------- |
| Journal maintenance           | Installed obsidian-journal Lua workflow                     | Unchanged                                                 |
| Topic/phrase renewal          | Installed journal glados.py, newer than standalone checkout | This skill; executing agent supplies text                 |
| Completion selection/throttle | Nix speech.py calling journal helper                        | This skill's completion adapter                           |
| Synthesis/playback            | Existing glados-say                                         | Existing glados-say                                       |
| Agent hook registration       | Nix installer and existing local settings                   | Explicit skill registration after legacy source migration |

The legacy Nix installer registers request/tool/permission/Stop events. The existing speech
implementation filters playback to Stop. The new registrar refuses known legacy glados-hook commands
rather than silently adding a second speaker. Journal direct-call migration and the Nix declaration
change remain cutover steps, not changes performed by installation.

No hook trust records, active voice settings, journal files or remote hosts were changed during
source implementation. Use [integration.md](integration.md) for verification gates, migration and
rollback.
