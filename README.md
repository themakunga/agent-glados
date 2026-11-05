# GLaDOS

<!-- cspell:ignore pkgs -->

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](#requirements)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)](#requirements)
[![Languages](https://img.shields.io/badge/docs-Espa%C3%B1ol%20%7C%20English-blue)](#español)
[![Voice](https://img.shields.io/badge/voice-opt--in-orange)](#english)

[Español](#español) · [English](#english)

## Español

### De qué se trata

Una skill para agentes de programación que renueva un catálogo de frases cortas y sarcásticas en
inglés, al estilo de GLaDOS, y reproduce una frase al completar una tarea cuando la voz está
autorizada. La personalidad se mantiene en un documento configurable.

- El agente redacta dos frases por proyecto habilitado una vez al día local; el helper valida y
  guarda el catálogo. No incluye un servicio de generación, una API de modelos ni un programador de
  tareas.
- Las frases diarias caducan a los siete días durante la renovación del proyecto.
- La reproducción se limita a los directorios permitidos y a una vez cada 90 segundos por sesión de
  cada agente. Los proyectos privados o deshabilitados permanecen en silencio.
- La renovación y el permiso de voz se configuran por separado. El journal mantiene su propio flujo
  de trabajo y no controla las frases ni el audio.

### Requisitos

| Requisito                                  | Uso                                                                                 |
| ------------------------------------------ | ----------------------------------------------------------------------------------- |
| macOS o Linux                              | El helper utiliza bloqueos POSIX mediante `fcntl`.                                  |
| Python 3.11 o superior                     | Ejecutar los scripts.                                                               |
| PyYAML y jsonschema                        | Leer YAML y validar configuración y catálogo.                                       |
| Un vault amgmt existente bajo `~/.vaults/` | Guardar la configuración y el catálogo compartidos.                                 |
| Un agente compatible                       | Leer la skill y redactar las frases.                                                |
| Git                                        | Clonar este repositorio; sincronizar el vault si corresponde.                       |
| `glados-agent` en `~/.local/bin/`          | Ejecutar los hooks registrados; debe proporcionarlo la configuración del host.      |
| `glados-say` en `PATH`                     | Solo para activar la voz; requiere un motor de síntesis y reproducción configurado. |

Las dependencias y los comandos del host se declaran mediante Nix en `nix-systems`, siguiendo WF-09
del entorno. Este repositorio no instala esos comandos ni el motor de voz. Para disponer de las
bibliotecas Python, la expresión de paquete es:

```nix
pkgs.python3.withPackages (ps: [ ps.pyyaml ps.jsonschema ])
```

### Instalación

1. Clona el repositorio en una ubicación permanente. El instalador enlaza la skill a esta ruta.

   ```sh
   git clone https://github.com/themakunga/agent-glados.git
   cd agent-glados/skills/glados
   python3 -c 'import yaml, jsonschema'
   python3 scripts/install.py
   ```

2. Selecciona el vault amgmt existente, los agentes, los proyectos y sus permisos. Puedes dejar la
   voz deshabilitada. El instalador muestra la configuración y los enlaces antes de pedir
   confirmación; preserva el catálogo existente y respalda la configuración anterior.

3. Valida la instalación y consulta qué proyectos necesitan frases:

   ```sh
   python3 scripts/glados.py --agent codex validate
   python3 scripts/glados.py --agent codex due
   ```

   Sustituye `codex` por tu agente. Para otro vault, añade `--vault /ruta/al/vault` antes del
   comando (`validate` o `due`). Sigue [SKILL.md](skills/glados/SKILL.md) para la renovación diaria.

4. Para automatizar los eventos, comprueba primero el comando del host y registra el adaptador:

   ```sh
   test -x "$HOME/.local/bin/glados-agent"
   python3 scripts/integrate.py --agent codex
   ```

   Ejecuta el registro solo cuando la comprobación anterior funcione. Revisa la vista previa,
   confirma el registro y completa la aprobación nativa de hooks del agente cuando corresponda.
   Reinicia la sesión y verifica el comportamiento real. Registrar hooks no demuestra que se hayan
   ejecutado.

### Agentes e integración

| Agente                     | Adaptador incluido                      | Verificación necesaria                                                     |
| -------------------------- | --------------------------------------- | -------------------------------------------------------------------------- |
| Codex                      | Solicitud y finalización                | Eventos, confianza nativa y sesión nueva.                                  |
| Claude Code                | Solicitud y finalización                | Eventos y sesión nueva.                                                    |
| Hermes                     | Antes y después de la llamada al modelo | Compatibilidad de la versión instalada y aprobación de hooks.              |
| Gemini, OpenClaw, ZeroClaw | Descubrimiento de la skill              | Renovación siguiendo sus instrucciones; sin adaptador automático incluido. |

La voz necesita habilitación global, del agente, del proyecto y del evento de finalización, además
de un directorio permitido, una sesión identificable y frases válidas. Excluye secretos,
credenciales y contenido confidencial al redactar frases.

Consulta la [guía de integración y migración](skills/glados/references/integration.md), la
[configuración de ejemplo](skills/glados/templates/config.example.yaml) y la
[evidencia de compatibilidad](skills/glados/references/inventory.md).

## English

### What it does

A coding-agent skill that renews a catalog of short, sarcastic English phrases in the style of
GLaDOS and plays a phrase when a task completes, when voice is authorized. Personality stays in a
configurable document.

- The agent writes two phrases per enabled project once per local day; the helper validates and
  saves the catalog. There is no generation service, model API or scheduler.
- Daily phrases expire after seven days during that project's renewal.
- Playback is limited to allowed directories and once every 90 seconds per agent session. Private or
  disabled projects remain silent.
- Renewal and voice permissions are separate. The journal keeps its own workflow and does not
  control phrases or audio.

### Requirements

| Requirement                                  | Purpose                                                                    |
| -------------------------------------------- | -------------------------------------------------------------------------- |
| macOS or Linux                               | The helper uses POSIX locks through `fcntl`.                               |
| Python 3.11 or later                         | Run the scripts.                                                           |
| PyYAML and jsonschema                        | Read YAML and validate configuration and catalog.                          |
| An existing amgmt vault beneath `~/.vaults/` | Store shared configuration and catalog.                                    |
| A compatible agent                           | Read the skill and write phrases.                                          |
| Git                                          | Clone this repository; synchronize the vault when applicable.              |
| `glados-agent` in `~/.local/bin/`            | Run registered hooks; supplied by the host configuration.                  |
| `glados-say` on `PATH`                       | Only to enable voice; requires a configured synthesis and playback engine. |

Declare dependencies and host commands through Nix in `nix-systems`, following the environment's
WF-09 workflow. This repository does not install those commands or the voice engine. The Python
package expression is:

```nix
pkgs.python3.withPackages (ps: [ ps.pyyaml ps.jsonschema ])
```

### Installation

1. Clone the repository to a permanent location. The installer links the skill to this path.

   ```sh
   git clone https://github.com/themakunga/agent-glados.git
   cd agent-glados/skills/glados
   python3 -c 'import yaml, jsonschema'
   python3 scripts/install.py
   ```

2. Select the existing amgmt vault, agents, projects and permissions. Voice can remain disabled. The
   installer previews configuration and discovery links before asking for confirmation, preserves
   the existing catalog and backs up the previous configuration.

3. Validate the installation and list projects that need phrases:

   ```sh
   python3 scripts/glados.py --agent codex validate
   python3 scripts/glados.py --agent codex due
   ```

   Replace `codex` with your agent. For another vault, add `--vault /path/to/vault` before the
   subcommand. Follow [SKILL.md](skills/glados/SKILL.md) for daily renewal.

4. To automate lifecycle events, check the host command first, then register the adapter:

   ```sh
   test -x "$HOME/.local/bin/glados-agent"
   python3 scripts/integrate.py --agent codex
   ```

   Run registration only after the preceding check succeeds. Review the preview, confirm
   registration and complete the agent's native hook approval where required. Restart the session
   and verify actual behavior. Registered hooks do not establish that they have executed.

### Agents and integration

| Agent                      | Included adapter                | Required verification                                          |
| -------------------------- | ------------------------------- | -------------------------------------------------------------- |
| Codex                      | Request and completion          | Events, native trust and a fresh session.                      |
| Claude Code                | Request and completion          | Events and a fresh session.                                    |
| Hermes                     | Before and after the model call | Installed-version compatibility and hook approval.             |
| Gemini, OpenClaw, ZeroClaw | Skill discovery                 | Renewal by following the skill; no automatic adapter included. |

Voice requires global, agent, project and completion-event permission, plus an allowed directory, an
identifiable session and valid phrases. Exclude secrets, credentials and confidential content when
writing phrases.

See the [integration and migration guide](skills/glados/references/integration.md),
[example configuration](skills/glados/templates/config.example.yaml) and
[compatibility evidence](skills/glados/references/inventory.md).
