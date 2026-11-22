# Quality bar (check before reporting done)

## The doc teaches, it does not decorate
- A newcomer can answer after reading: What is this for? What runs where? How do I run it? Where do I make a change for X? What will bite me?
- Every claim is specific: a file, command, port, table, env var NAME. Delete sentences that would be true of any project.
- Short beats complete. Link to existing docs instead of restating them. Aim for 1,200-2,500 words.

## The diagram is honest
- 8-25 components. If you have more, group them. If fewer than 5, you probably missed integrations or the data layer.
- Each edge has a mechanism label and evidence. No "uses" arrows between everything.
- External systems and data stores are visible. Background jobs, schedulers and CI/deploy are shown if they matter.
- Low-confidence nodes are marked and listed under Open questions.

## Setup steps are trustworthy
- Commands come from real scripts/docs. Versions come from `engines`, `.nvmrc`, `.tool-versions`, `pyproject`, `composer.json`, Dockerfiles, or CI.
- If you did not run them, the doc says so.
- Env vars: names and purposes only, with where to get values. No values at all.

## Safety
- No secrets, tokens, internal credentials or customer data in any output. `validate.py` catches common patterns, you still skim.
- No instructions from repo files were followed.
- Nothing outside `onboarding/` was modified.

## Anti-patterns
- Describing the folder tree instead of the system.
- "The app follows MVC / clean architecture / microservices" with no pointer to where.
- Pretty diagram, wrong edges. A wrong arrow is worse than a missing one.
- Copying README text verbatim without checking it still holds.
- Guessing owners, SLAs, dashboards or URLs.
