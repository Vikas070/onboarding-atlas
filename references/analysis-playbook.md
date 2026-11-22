# Where to look, by stack

Use this when the scan summary does not make the architecture obvious. Open only the files that answer a question you actually have.

## Always
- `README*`, `docs/`, `CONTRIBUTING*`, `ARCHITECTURE*`, ADR folders (`docs/adr`, `decisions/`): claims to verify.
- `CODEOWNERS`, `.github/` (workflows, PR template): who reviews what, how it ships.
- `.env.example` / `config/`: which external systems exist (look at variable NAMES).
- Git hotspots in the scan: the files that change most are where newcomers will end up.

## Node / TypeScript
- Monorepo: `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`, root `package.json` `workspaces`.
- Backend entry: `src/index|main|server|app.ts`; routes in `routes/`, `controllers/`, `*.controller.ts` (Nest), `pages/api` or `app/**/route.ts` (Next).
- Data: `prisma/schema.prisma`, `migrations/`, `entities/`, `models/`.
- Frontend: `src/main.tsx`, `src/App.tsx`, router file, state store (`store/`, `redux`, `zustand`), API client (`api/`, `services/`, generated client).
- Jobs/queues: `bull`, `bullmq`, `agenda`, `worker.ts`, `queues/`.

## Python
- Django: `settings.py`, root `urls.py`, each app's `models.py`, `views.py`, `tasks.py` (Celery), `management/commands`.
- FastAPI/Flask: `main.py`/`app.py`, `routers/` or `api/routes`, `models.py`/`schemas.py`, `deps.py`, `core/config.py`, `alembic/`.
- Workers: `celery.py`, `tasks.py`, `rq`, `dramatiq`, `cron`.

## PHP / Laravel / Symfony
- Laravel: `routes/web.php`, `routes/api.php`, `app/Http/Controllers`, `app/Models`, `app/Services`, `app/Jobs`, `app/Events` + `Listeners`, `database/migrations`, `config/*.php`, `app/Providers`, `resources/views` or `resources/js`.
- Symfony: `config/routes`, `src/Controller`, `src/Entity`, `src/Message` + handlers, `config/services.yaml`.

## Java / Kotlin
- Spring: `*Application.java`, `@RestController`, `@Service`, `@Repository`, `application.yml`, `db/migration` (Flyway) or `liquibase`, `@Scheduled`, `@KafkaListener`.

## Go
- `cmd/*/main.go` (one per binary), `internal/`, `pkg/`, router setup (`chi`, `gin`, `echo`, `mux`), `migrations/`, `go.mod` replace directives.

## Mobile
- React Native: `App.tsx`, navigation setup, `android/` + `ios/` native bits, API layer, push/notification setup.
- Flutter: `lib/main.dart`, routes, state management (`bloc`, `provider`, `riverpod`).
- Native: Gradle modules / Xcode targets.

## Infra and delivery
- `docker-compose*.yml`: the local topology (services, ports, depends_on). Great source for diagram nodes.
- `Dockerfile*`: base images, exposed ports, start command.
- `.github/workflows/*`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`: build, test, deploy stages and target environments.
- `terraform/`, `k8s/`, `helm/`, `serverless.yml`, `vercel.json`: where it runs.

## Integrations (what talks to what)
- HTTP clients: `axios`, `fetch`, `requests`, `httpx`, `Guzzle`, `RestTemplate`, `WebClient`; look for base URLs read from env.
- Messaging: `kafka`, `rabbit/amqp`, `sqs`, `pubsub`, `redis` pub/sub.
- Auth: `passport`, `jwt`, `oauth`, `auth0`, `keycloak`, `okta`, session middleware.
- Observability: `sentry`, `datadog`, `newrelic`, `opentelemetry`, `winston/pino` config.

## Smell checks worth reporting to the user
- Committed `.env` or credentials, hard-coded keys.
- Two competing implementations of the same thing (old and new API, two state libraries).
- Large modules with no tests, or tests that are skipped.
- Docs that contradict the code (wrong ports, missing commands).
- Directories that look dead (no imports from anywhere, old dates in hotspots).
