# onboarding-atlas

Give any coding agent (Claude Code, Codex, Cursor, others) one instruction and get, for the repo it has open:

- `onboarding/ONBOARDING.md`: a written onboarding guide (what it is, how it fits together, how to run it, flows, gotchas, first week).
- `onboarding/architecture.html`: a single offline page with a clickable architecture diagram, animated request flows, a setup checklist and a code map. Email it, host it, or open it from disk.
- A verification step that checks every file path, command and env var the agent wrote against the real repo, and blocks leaked secrets.

No server, no database, no dependencies beyond Python 3 (standard library only). Nothing leaves your machine except whatever your coding agent already sends to its own model.

## Install

Pick one. All of them only copy files (no network after download, no sudo, no postinstall scripts).

**A. npx** (needs Node 16.7+; works on Windows, Mac, Linux)
```sh
npx onboarding-atlas init                 # current project, all agents
npx onboarding-atlas init /path/to/project --claude     # one agent: --claude | --codex | --cursor
npx onboarding-atlas init --global-claude # Claude Code, every project
npx onboarding-atlas doctor               # checks Python 3.8+
```

**B. One-line web install** (Mac/Linux; pin a tag and ideally a checksum)
```sh
curl -fsSL https://raw.githubusercontent.com/Vikas070/onboarding-atlas/v1.0.1/get.sh \
  | OA_SHA256=<sha256 of the release tarball> sh -s -- /path/to/project --claude
```
Prefer to read first? Download `get.sh`, open it, then run `sh get.sh /path/to/project`.

**C. From a clone or zip**
```sh
git clone --depth 1 --branch v1.0.1 https://github.com/Vikas070/onboarding-atlas
sh onboarding-atlas/install.sh /path/to/project
```

**D. Manual (any agent, any OS)**: copy this folder into the project as `.agents/skills/onboarding-atlas/` and tell the agent: "Follow .agents/skills/onboarding-atlas/SKILL.md".

The Codex and Cursor locations follow current conventions (`AGENTS.md`, `.cursor/rules`). If your version looks elsewhere, use option D.

## Use

In your coding agent, from the repo root:

> Use the onboarding-atlas skill to document this repo.

Add context if useful: "the reader is a client's project manager", or "only the `services/billing` part".

## What is deterministic and what is AI

| Step | Who | Why |
|---|---|---|
| Inventory: languages, modules, import graph, routes, models, env var names, compose services, CI, scripts, hotspots | `scripts/scan.py` | Repeatable, no hallucination |
| Understanding: what components mean, how they connect across services, setup narrative | The agent, reading the code | Needs judgment |
| Checking: file paths, commands, env vars, coverage, secrets | `scripts/validate.py` | The agent cannot grade its own work |
| The diagram page | `scripts/build_diagram.py` + `templates/diagram.html` | Same look every time, offline |

## Known limits (be aware)

- The import graph covers JS/TS, Python, PHP, Go, Java and Kotlin. Other languages are listed but their dependencies are not resolved. Calls between services (HTTP, queues) are never visible to the scanner; the agent must find them by reading code, and the doc marks what it could not confirm.
- The scanner never stores environment variable values. If a `.env` file is tracked in git it reads the variable names only and reports the file so you can check it.
- The output is a snapshot of one commit (shown in the page footer). Re-run the skill to refresh; it updates incrementally.
- Auto-generated onboarding material should be skimmed by a teammate before it goes to a client.

## Layout

```
SKILL.md                      the instructions the agent follows
scripts/scan.py               repo scanner  -> onboarding/scan.json
scripts/build_diagram.py      architecture.json -> architecture.html
scripts/validate.py           verification gate
templates/diagram.html        interactive page (vanilla JS, no CDN)
templates/ONBOARDING.template.md
references/                   schema, per-stack playbook, quality bar
adapters/                     Codex/Cursor pointers
install.sh
```

## Publishing your own copy (maintainer notes)

1. Already done for this copy: `LICENSE` has your name and `Vikas070` is set in `package.json`, `get.sh` and this README. If you fork or rename, update those three files.
2. Push to GitHub and create a release tag, for example `v1.0.1`. The tag is what `get.sh` downloads.
3. Checksum for the web installer: `curl -fsSL https://github.com/<you>/onboarding-atlas/archive/refs/tags/v1.0.1.tar.gz | shasum -a 256` and put the value in the install docs.
4. npm: `npm login`, then `npm publish --access public`. Check the name `onboarding-atlas` is free first (`npm view onboarding-atlas`); if taken, use a scoped name such as `@yourname/onboarding-atlas` and update `package.json`.
5. Bump `version` in `package.json` and tag again for every change; never re-point an existing tag.
