# <Project name>: onboarding guide

<!-- Replace every <...>. Delete these comments. Backtick only real repo paths (they are verified). -->

> Generated from commit `<sha>` on <date>. Interactive version: [architecture.html](architecture.html). Verify anything critical against the code.

## TL;DR

<!-- 3-5 sentences: what the system is, who uses it, the main technologies, and the one thing a newcomer must know first.
     If the reader is a client/non-technical: one extra paragraph "What it does for the business". -->

## Architecture at a glance

<!-- 1 short paragraph, then a bullet list of the main components with deep links to the diagram.
     Example: - **Orders API**: Laravel REST API for orders and invoices ([see in diagram](architecture.html#node=api)) -->

- **<Component>**: <one line> ([diagram](architecture.html#node=<id>))

How the pieces talk to each other: <2-4 sentences: protocols, queues, who calls whom>.

## Repository map

<!-- Table of the top-level folders that matter. Skip folders nobody needs. -->

| Path | What lives here |
|---|---|
| `<dir/>` | <one line> |

## Local setup

<!-- Ordered, copy-pasteable. Source every command from real scripts/docs. Say which steps you did NOT execute. -->

**Prerequisites:** <runtime versions, tools, accounts>

1. <Step>: `<command>`
2. <Step>: `<command>`

**You know it works when:** <observable result: URL, test output, log line>.

**Not executed:** these steps come from the repo's docs and scripts; they were not run while writing this guide.

### Configuration

<!-- Env var NAMES and meaning only. Say where real values come from (secret store, teammate, vault). Never values. -->

| Variable | Purpose | Required |
|---|---|---|
| `<NAME>` | <purpose> | yes/no |

## Key flows

<!-- 2-4 journeys, each 3-7 numbered steps naming the files involved. Deep link: architecture.html#flow=<id> -->

### <Flow title> ([animated in diagram](architecture.html#flow=<id>))

1. <Step at component, file `path`>
2. <...>

## Data model

<!-- Main entities and relationships in a few lines; where the schema/migrations live; how to run migrations. -->

## Testing

<!-- Frameworks, how to run, what is covered, what is not, how CI runs them. -->

## Build, CI/CD and environments

<!-- Pipeline stages, environments, how a change reaches production, who/what approves it. Only what you saw. -->

## Conventions and gotchas

<!-- Naming, folder rules, lint/format, branching, and the surprising things you verified. Bullets. -->

## Who and what to ask

<!-- Only if the repo states owners (CODEOWNERS, docs). Otherwise write: "No owners are recorded in the repo." -->

## First week

<!-- Concrete, small, safe: run it, read X, trace flow Y, fix a label in Z, run the tests. 5-8 checkboxes. -->

- [ ] <task>

## Open questions / unverified

<!-- Everything you could not confirm, as questions a teammate can answer in one line. -->

- <question>
