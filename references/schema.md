# architecture.json schema

Written by the agent into `onboarding/architecture.json`. `build_diagram.py` and `validate.py` enforce it.
Text fields are plain text (no HTML/Markdown). Keep sentences short.

## Top level

| Field | Required | Notes |
|---|---|---|
| `project` | yes | `{name, summary, audience?}`. `summary`: 1-2 sentences, what the system does and how, no marketing. |
| `layers` | recommended | Ordered list `{id, label}`. Rendered as columns left to right. Order = direction a request travels. |
| `nodes` | yes | Components, 8-25 of them. |
| `edges` | yes | Connections between nodes. |
| `flows` | recommended | 2-4 step-by-step journeys. |
| `setup` | recommended | `{prerequisites[], steps[], env[]}` |
| `glossary` | optional | `[{term, def}]` project-specific words only. |
| `open_questions` | recommended | Strings. Everything unverified. |

## node

| Field | Required | Notes |
|---|---|---|
| `id` | yes | lowercase letters, digits, `-`, `_`. Used in deep links: `architecture.html#node=<id>`. |
| `label` | yes | Short name, 1-4 words (about 22 characters max shown). |
| `layer` | yes | One of `layers[].id`. |
| `kind` | yes | `ui api service db cache queue external job library infra storage search auth cli docs other` |
| `description` | yes | 1-3 sentences: what it is and what it is responsible for. |
| `responsibilities` | no | Up to ~5 bullets. |
| `tech` | no | Real technologies seen in the code, for example `["Express", "TypeScript"]`. |
| `files` | yes for internal nodes | Existing paths or directories (relative to repo root). Trailing `/` allowed. Optional `:line`. |
| `run` | no | A command that starts or exercises just this component. |
| `gotchas` | no | Surprises, sharp edges, "do not touch" facts you verified. |
| `owner` | no | Only if the repo says so (CODEOWNERS, docs). Never guess. |
| `confidence` | no | `"low"` if inferred or only skimmed. Shows a warning badge. Must also appear in `open_questions`. |

## edge

| Field | Required | Notes |
|---|---|---|
| `from`, `to` | yes | Node ids. Direction = who initiates or depends on whom. |
| `label` | recommended | The mechanism: "REST", "GraphQL", "enqueues job", "reads/writes", "imports", "webhook". |
| `kind` | no | Free text, for example `calls`, `reads`, `publishes`. |
| `evidence` | recommended | Paths of files that show the connection. Verified to exist. |

## flow

```json
{"id": "login", "title": "User logs in", "description": "optional",
 "steps": [{"node": "web", "text": "Form posts credentials to /api/login."},
           {"node": "api", "text": "Validates, issues a JWT."}]}
```
Steps are ordered. Each `node` must exist. `text` says what happens at that component, in one sentence.

## setup

```json
{"prerequisites": ["Node.js 22", "Docker"],
 "steps": [{"title": "Install", "cmd": "pnpm install", "note": "optional", "expect": "optional success signal"}],
 "env": [{"key": "DATABASE_URL", "purpose": "Postgres connection string", "required": true}]}
```
Env entries are NAMES only. Never include values, even "example" passwords.

## Minimal example

```json
{
  "project": {"name": "Acme Orders", "summary": "A Laravel API and React admin for managing customer orders, backed by MySQL and a Redis queue."},
  "layers": [{"id": "client", "label": "Clients"}, {"id": "app", "label": "Application"}, {"id": "data", "label": "Data"}],
  "nodes": [
    {"id": "admin-ui", "label": "Admin UI", "layer": "client", "kind": "ui", "description": "React single-page app used by support staff.", "tech": ["React"], "files": ["admin/src/"]},
    {"id": "api", "label": "Orders API", "layer": "app", "kind": "api", "description": "Laravel REST API: auth, orders, invoices.", "tech": ["Laravel"], "files": ["app/Http/Controllers/", "routes/api.php"]},
    {"id": "db", "label": "MySQL", "layer": "data", "kind": "db", "description": "Primary store for orders and customers.", "files": ["database/migrations/"]}
  ],
  "edges": [
    {"from": "admin-ui", "to": "api", "label": "REST/JSON", "evidence": ["admin/src/api/client.ts"]},
    {"from": "api", "to": "db", "label": "Eloquent reads/writes", "evidence": ["app/Models/Order.php"]}
  ],
  "flows": [{"id": "place-order", "title": "Place an order", "steps": [
    {"node": "admin-ui", "text": "Staff submits the order form."},
    {"node": "api", "text": "OrderController@store validates and saves."},
    {"node": "db", "text": "Row inserted into orders."}]}],
  "setup": {"prerequisites": ["PHP 8.3", "Composer"], "steps": [{"title": "Install", "cmd": "composer install"}], "env": [{"key": "DB_HOST", "purpose": "MySQL host"}]},
  "open_questions": ["How are invoices PDFs generated? Not found in app/."]
}
```
