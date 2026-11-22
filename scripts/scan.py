#!/usr/bin/env python3
"""onboarding-atlas scanner.

Read-only, stdlib-only (Python 3.8+). Walks a repository and writes a factual
inventory to <out>/scan.json plus a compact summary on stdout.

Everything here is deterministic and carries file-path evidence. The AI agent
uses it as a map, then reads the real code to write the onboarding material.

Safety:
  * real .env files (only seen when committed/untracked-and-not-ignored) are parsed for variable NAMES only;
    values are discarded in-process and never written to scan.json or printed
  * never prints or stores environment variable VALUES
  * git remote URLs are stripped of credentials
  * contributor names are only included with --include-authors

Usage:
  python3 scan.py [repo_path] [--out DIR] [--max-files N] [--include-authors]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor", "dist", "build",
    "out", ".next", ".nuxt", ".svelte-kit", ".turbo", ".cache", ".parcel-cache", "coverage",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", ".gradle", ".idea", ".vscode", ".terraform", "Pods", "DerivedData", ".dart_tool",
    "storage/framework", ".ua", ".understand-anything",
}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp", ".pdf", ".zip", ".gz", ".tar",
    ".tgz", ".7z", ".rar", ".jar", ".war", ".class", ".exe", ".dll", ".so", ".dylib", ".bin", ".woff",
    ".woff2", ".ttf", ".eot", ".otf", ".mp3", ".mp4", ".mov", ".avi", ".wav", ".lock", ".map",
    ".min.js", ".psd", ".ai", ".sketch", ".fig", ".pyc", ".o", ".a", ".sqlite", ".db",
}
LANG_BY_EXT = {
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".vue": "Vue", ".svelte": "Svelte",
    ".py": "Python", ".php": "PHP", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".cs": "C#", ".cpp": "C++", ".cc": "C++", ".c": "C",
    ".h": "C/C++ header", ".hpp": "C/C++ header", ".swift": "Swift", ".m": "Objective-C",
    ".dart": "Dart", ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir", ".lua": "Lua",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell", ".sql": "SQL", ".html": "HTML",
    ".css": "CSS", ".scss": "CSS", ".sass": "CSS", ".less": "CSS", ".tf": "Terraform",
    ".yml": "YAML", ".yaml": "YAML", ".json": "JSON", ".toml": "TOML", ".md": "Markdown",
    ".mdx": "Markdown", ".graphql": "GraphQL", ".gql": "GraphQL", ".proto": "Protobuf",
    ".prisma": "Prisma", ".blade.php": "PHP",
}
CODE_LANGS = {
    "JavaScript", "TypeScript", "Vue", "Svelte", "Python", "PHP", "Java", "Kotlin", "Go", "Rust",
    "Ruby", "C#", "C++", "C", "Swift", "Objective-C", "Dart", "Scala", "Elixir", "Lua", "Shell",
    "SQL", "PowerShell",
}
IMPORT_RESOLVED = {"JavaScript", "TypeScript", "Vue", "Svelte", "Python", "PHP", "Go", "Java", "Kotlin"}
CONTAINERS = {
    "packages", "apps", "services", "libs", "modules", "plugins", "cmd", "internal", "pkg", "src",
    "app", "lib", "server", "client", "backend", "frontend", "api", "web", "projects", "crates",
}
MAX_READ = 1_000_000
JS_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".json"]


# ---------------------------------------------------------------- file listing
def run(cmd, cwd, timeout=25):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
    except Exception:
        return None


def list_files(root, max_files, skip_prefix=None):
    files = []
    out = None
    if os.path.isdir(os.path.join(root, ".git")) or run(["git", "rev-parse", "--git-dir"], root):
        raw = run(["git", "ls-files", "-z", "-co", "--exclude-standard"], root)
        if raw:
            out = [p for p in raw.split("\0") if p]
    if out is None:
        out = []
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.startswith(".git")]
            for f in fn:
                out.append(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/"))
    for p in out:
        parts = p.split("/")
        if any(seg in SKIP_DIRS for seg in parts[:-1]):
            continue
        if "skills/onboarding-atlas/" in p + "/" or p.startswith(".cursor/rules/onboarding-atlas"):
            continue  # this tool's own installed files are not the project's code
        if skip_prefix and (p == skip_prefix or p.startswith(skip_prefix + "/")):
            continue  # our own output folder, not the project's code
        if not os.path.isfile(os.path.join(root, p)):
            continue
        files.append(p)
    files.sort()
    truncated = len(files) > max_files
    return files[:max_files], truncated


def ext_of(p):
    b = os.path.basename(p).lower()
    if b.endswith(".blade.php"):
        return ".blade.php"
    if b.endswith(".min.js"):
        return ".min.js"
    return os.path.splitext(b)[1]


def read_text(root, p, limit=MAX_READ):
    fp = os.path.join(root, p)
    try:
        if os.path.getsize(fp) > limit:
            return None
        with open(fp, "rb") as f:
            data = f.read()
        if b"\0" in data[:4096]:
            return None
        return data.decode("utf-8", "replace")
    except Exception:
        return None


def is_secret_env_file(p):
    b = os.path.basename(p).lower()
    if not (b == ".env" or b.startswith(".env.") or b.endswith(".env")):
        return False
    return not any(s in b for s in ("example", "sample", "template", "dist", "defaults"))


# ---------------------------------------------------------------- modules
def adaptive_modules(paths, threshold=120, max_depth=4):
    assign = {}

    def rec(prefix, items, depth):
        forced = depth == 0 or (prefix and prefix[-1].lower() in CONTAINERS and len(prefix) == depth)
        if not forced and (len(items) <= threshold or depth >= max_depth):
            name = "/".join(prefix) or "(root)"
            for p in items:
                assign[p] = name
            return
        groups = defaultdict(list)
        for p in items:
            parts = p.split("/")
            if len(parts) <= depth + 1:
                groups[None].append(p)
            else:
                groups[parts[depth]].append(p)
        for key, lst in groups.items():
            if key is None:
                name = "/".join(prefix) or "(root)"
                for p in lst:
                    assign[p] = name
            else:
                rec(prefix + [key], lst, depth + 1)

    rec([], list(paths), 0)
    return assign


ROLE_HINTS = [
    ("test", r"(^|/)(tests?|__tests__|spec|specs|e2e|cypress|playwright)(/|$)"),
    ("infra", r"(^|/)(infra|terraform|k8s|kubernetes|helm|deploy|docker|\.github|ci|ops|charts)(/|$)"),
    ("data", r"(^|/)(migrations?|models?|entities|entity|schema|prisma|db|database|seeds?|repositor(y|ies))(/|$)"),
    ("api", r"(^|/)(api|routes?|controllers?|handlers?|endpoints?|resolvers?|http|rest|graphql)(/|$)"),
    ("ui", r"(^|/)(components?|pages|views?|screens?|ui|web|frontend|client|public|templates|resources/views|styles?)(/|$)"),
    ("service", r"(^|/)(services?|domain|usecases?|core|business|jobs?|workers?|queues?|commands?)(/|$)"),
    ("shared", r"(^|/)(utils?|lib|libs|common|shared|helpers?|types|config|constants)(/|$)"),
    ("docs", r"(^|/)(docs?|documentation|READMEs?|homepage|assets|examples?)(/|$)"),
    ("scripts", r"(^|/)(scripts?|tools?|bin)(/|$)"),
]


def role_guess(mod):
    for role, pat in ROLE_HINTS:
        if re.search(pat, mod + "/", re.I):
            return role
    return "unknown"


# ---------------------------------------------------------------- manifests
def load_json(root, p):
    t = read_text(root, p)
    if t is None:
        return None
    try:
        return json.loads(t)
    except Exception:
        t2 = re.sub(r"^\s*//.*$", "", t, flags=re.M)
        t2 = re.sub(r"/\*.*?\*/", "", t2, flags=re.S)
        t2 = re.sub(r",(\s*[}\]])", r"\1", t2)
        try:
            return json.loads(t2)
        except Exception:
            return None


FRAMEWORK_KEYS = {
    "react": "React", "next": "Next.js", "vue": "Vue", "nuxt": "Nuxt", "@angular/core": "Angular",
    "svelte": "Svelte", "@sveltejs/kit": "SvelteKit", "react-native": "React Native", "expo": "Expo",
    "express": "Express", "fastify": "Fastify", "@nestjs/core": "NestJS", "koa": "Koa", "hono": "Hono",
    "electron": "Electron", "vite": "Vite", "webpack": "Webpack", "redux": "Redux",
    "@reduxjs/toolkit": "Redux Toolkit", "tailwindcss": "Tailwind CSS", "graphql": "GraphQL",
    "@apollo/client": "Apollo Client", "apollo-server": "Apollo Server", "trpc": "tRPC",
    "@trpc/server": "tRPC", "typescript": "TypeScript", "jest": "Jest", "vitest": "Vitest",
    "mocha": "Mocha", "cypress": "Cypress", "@playwright/test": "Playwright", "storybook": "Storybook",
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI", "celery": "Celery", "pytest": "pytest",
    "sqlalchemy": "SQLAlchemy", "laravel/framework": "Laravel", "symfony/framework-bundle": "Symfony",
    "phpunit/phpunit": "PHPUnit", "spring-boot": "Spring Boot", "rails": "Rails", "gin-gonic/gin": "Gin",
    "labstack/echo": "Echo", "gofiber/fiber": "Fiber", "tauri": "Tauri",
}
SERVICE_KEYS = [
    # (substring in dep/image/env name, label, kind)
    ("postgres", "PostgreSQL", "db"), ("psycopg", "PostgreSQL", "db"), ("pg", "PostgreSQL", "db"),
    ("mysql", "MySQL", "db"), ("mariadb", "MariaDB", "db"), ("mongo", "MongoDB", "db"),
    ("sqlite", "SQLite", "db"), ("redis", "Redis", "cache"), ("memcache", "Memcached", "cache"),
    ("elasticsearch", "Elasticsearch", "search"), ("opensearch", "OpenSearch", "search"),
    ("algolia", "Algolia", "search"), ("kafka", "Kafka", "queue"), ("rabbit", "RabbitMQ", "queue"),
    ("amqp", "AMQP broker", "queue"), ("bullmq", "BullMQ", "queue"), ("sqs", "AWS SQS", "queue"),
    ("celery", "Celery", "queue"), ("sidekiq", "Sidekiq", "queue"), ("aws-sdk", "AWS", "external"),
    ("boto3", "AWS", "external"), ("s3", "AWS S3", "external"), ("firebase", "Firebase", "external"),
    ("supabase", "Supabase", "external"), ("stripe", "Stripe", "external"), ("twilio", "Twilio", "external"),
    ("sendgrid", "SendGrid", "external"), ("mailgun", "Mailgun", "external"),
    ("sentry", "Sentry", "external"), ("datadog", "Datadog", "external"), ("newrelic", "New Relic", "external"),
    ("openai", "OpenAI API", "external"), ("anthropic", "Anthropic API", "external"),
    ("@azure", "Azure", "external"), ("google-cloud", "Google Cloud", "external"),
    ("auth0", "Auth0", "external"), ("okta", "Okta", "external"), ("keycloak", "Keycloak", "external"),
    ("socket.io", "Socket.IO", "realtime"), ("prisma", "Prisma ORM", "orm"), ("typeorm", "TypeORM", "orm"),
    ("sequelize", "Sequelize", "orm"), ("mongoose", "Mongoose", "orm"), ("eloquent", "Eloquent", "orm"),
    ("hibernate", "Hibernate", "orm"), ("snowflake", "Snowflake", "db"), ("bigquery", "BigQuery", "db"),
    ("superset", "Apache Superset", "external"), ("clickhouse", "ClickHouse", "db"),
]
SERVICE_SHORT = {"pg", "s3", "sqs"}  # match only as exact dep name / image


def detect_services(names_with_src):
    found = {}
    for name, src in names_with_src:
        low = name.lower()
        for key, label, kind in SERVICE_KEYS:
            hit = (low == key or low.startswith(key + "/")) if key in SERVICE_SHORT else key in low
            if hit:
                found.setdefault(label, {"label": label, "kind": kind, "evidence": []})
                if src not in found[label]["evidence"] and len(found[label]["evidence"]) < 3:
                    found[label]["evidence"].append(src)
    return list(found.values())


def parse_manifests(root, files):
    manifests, deps, frameworks, scripts = [], [], {}, []
    pkg_names = {}  # npm package name -> dir
    psr4 = {}
    go_module = None
    for p in files:
        b = os.path.basename(p)
        d = os.path.dirname(p)
        if b == "package.json":
            j = load_json(root, p)
            if not isinstance(j, dict):
                continue
            all_deps = {}
            for k in ("dependencies", "devDependencies", "peerDependencies"):
                if isinstance(j.get(k), dict):
                    all_deps.update(j[k])
            if j.get("name"):
                pkg_names[j["name"]] = d
            sc = j.get("scripts") if isinstance(j.get("scripts"), dict) else {}
            for k, v in list(sc.items())[:40]:
                scripts.append({"file": p, "name": k, "command": str(v)[:200]})
            manifests.append({
                "file": p, "type": "npm", "name": j.get("name"), "private": j.get("private"),
                "workspaces": j.get("workspaces"), "main": j.get("main"), "bin": j.get("bin"),
                "engines": j.get("engines"), "packageManager": j.get("packageManager"),
                "dependency_count": len(all_deps), "top_dependencies": sorted(all_deps)[:25],
            })
            for n in all_deps:
                deps.append((n, p))
                if n in FRAMEWORK_KEYS:
                    frameworks.setdefault(FRAMEWORK_KEYS[n], []).append(p)
        elif b == "composer.json":
            j = load_json(root, p)
            if not isinstance(j, dict):
                continue
            req = dict(j.get("require", {}) or {})
            req.update(j.get("require-dev", {}) or {})
            for ns, path in ((j.get("autoload") or {}).get("psr-4") or {}).items():
                for pp in (path if isinstance(path, list) else [path]):
                    psr4[ns] = (d + "/" if d else "") + pp.strip("/")
            for k, v in list((j.get("scripts") or {}).items())[:20]:
                scripts.append({"file": p, "name": k, "command": json.dumps(v)[:200]})
            manifests.append({"file": p, "type": "composer", "name": j.get("name"),
                              "dependency_count": len(req), "top_dependencies": sorted(req)[:25]})
            for n in req:
                deps.append((n, p))
                if n in FRAMEWORK_KEYS:
                    frameworks.setdefault(FRAMEWORK_KEYS[n], []).append(p)
        elif b in ("requirements.txt", "requirements-dev.txt", "requirements.in") or (
                b.startswith("requirements") and b.endswith(".txt")):
            t = read_text(root, p) or ""
            names = [re.split(r"[=<>~!\[; ]", l.strip(), 1)[0].lower() for l in t.splitlines()
                     if l.strip() and not l.strip().startswith(("#", "-"))]
            manifests.append({"file": p, "type": "pip", "dependency_count": len(names),
                              "top_dependencies": names[:25]})
            for n in names:
                deps.append((n, p))
                if n in FRAMEWORK_KEYS:
                    frameworks.setdefault(FRAMEWORK_KEYS[n], []).append(p)
        elif b == "pyproject.toml":
            t = read_text(root, p) or ""
            names = re.findall(r'^\s*"?([A-Za-z0-9_.\-]+)"?\s*(?:[=<>~!^]|$)', t, flags=re.M)
            proj = re.search(r'^name\s*=\s*"([^"]+)"', t, flags=re.M)
            manifests.append({"file": p, "type": "pyproject", "name": proj.group(1) if proj else None})
            low = t.lower()
            for n in FRAMEWORK_KEYS:
                if re.search(r'["\'\s]' + re.escape(n) + r'[\s"\'=<>~!\[]', low):
                    frameworks.setdefault(FRAMEWORK_KEYS[n], []).append(p)
                    deps.append((n, p))
        elif b == "go.mod":
            t = read_text(root, p) or ""
            m = re.search(r"^module\s+(\S+)", t, flags=re.M)
            if m and not go_module:
                go_module = (m.group(1), d)
            req = re.findall(r"^\s*([\w./\-]+)\s+v[\w.\-+]+", t, flags=re.M)
            manifests.append({"file": p, "type": "go", "name": m.group(1) if m else None,
                              "dependency_count": len(req), "top_dependencies": req[:25]})
            for n in req:
                deps.append((n, p))
                for k, v in FRAMEWORK_KEYS.items():
                    if k in n:
                        frameworks.setdefault(v, []).append(p)
        elif b in ("pom.xml", "build.gradle", "build.gradle.kts"):
            t = read_text(root, p) or ""
            manifests.append({"file": p, "type": "jvm"})
            for m in re.finditer(r"(?:artifactId>|['\"])([\w.\-]+)(?:<|['\":])", t):
                deps.append((m.group(1), p))
            if "spring-boot" in t:
                frameworks.setdefault("Spring Boot", []).append(p)
        elif b in ("Cargo.toml", "Gemfile", "pubspec.yaml", "Package.swift") or b.endswith(".csproj"):
            manifests.append({"file": p, "type": b})
            t = read_text(root, p) or ""
            if b == "Gemfile" and re.search(r"gem ['\"]rails['\"]", t):
                frameworks.setdefault("Rails", []).append(p)
    return manifests, deps, frameworks, scripts, pkg_names, psr4, go_module


# ---------------------------------------------------------------- imports
JS_IMPORT = re.compile(
    r"""(?:import|export)\s[^'"`;]*?from\s*['"]([^'"]+)['"]|import\s*['"]([^'"]+)['"]|"""
    r"""require\(\s*['"]([^'"]+)['"]\s*\)|import\(\s*['"]([^'"]+)['"]\s*\)""")
PY_FROM = re.compile(r"^\s*from\s+(\.*[\w.]*)\s+import\s+", re.M)
PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+)", re.M)
PHP_USE = re.compile(r"^\s*use\s+([\w\\]+)(?:\s+as\s+\w+)?\s*;", re.M)
GO_IMPORT_BLOCK = re.compile(r"import\s*\(([^)]*)\)", re.S)
GO_IMPORT_ONE = re.compile(r'import\s+(?:\w+\s+)?"([^"]+)"')
JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)


class Resolver:
    def __init__(self, root, files, pkg_names, psr4, go_module):
        self.root = root
        self.fileset = set(files)
        self.pkg_names = pkg_names
        self.psr4 = psr4
        self.go_module = go_module
        self.ts_aliases = []  # (prefix, [target dirs])
        self.py_index = {}
        self.java_index = {}
        self.dir_files = defaultdict(list)
        for f in files:
            self.dir_files[os.path.dirname(f)].append(f)
            if f.endswith(".py"):
                def dotted_of(path):
                    d = path[:-3].replace("/", ".")
                    return d[: -len(".__init__")] if d.endswith(".__init__") else d
                self.py_index.setdefault(dotted_of(f), f)
                # package root = first ancestor dir that is not itself a package (no __init__.py)
                parts = f.split("/")
                for i in range(len(parts) - 1):
                    anc = "/".join(parts[: i + 1])
                    if (anc + "/__init__.py") not in self.fileset:
                        rest = "/".join(parts[i + 1:])
                        if rest and rest != "__init__.py":
                            self.py_index.setdefault(dotted_of(rest), f)
                        break
                if f.startswith("src/"):
                    self.py_index.setdefault(dotted_of(f[4:]), f)
            if f.endswith((".java", ".kt")):
                m = re.search(r"(?:java|kotlin)/(.+)\.(?:java|kt)$", f)
                if m:
                    self.java_index.setdefault(m.group(1).replace("/", "."), f)
        for p in files:
            if os.path.basename(p) in ("tsconfig.json", "jsconfig.json", "tsconfig.base.json"):
                j = load_json(root, p)
                co = (j or {}).get("compilerOptions", {}) if isinstance(j, dict) else {}
                base = os.path.join(os.path.dirname(p), co.get("baseUrl", ".")).replace("\\", "/")
                base = os.path.normpath(base).replace("\\", "/")
                for k, v in (co.get("paths") or {}).items():
                    tgts = [os.path.normpath(os.path.join(base, t.rstrip("*").rstrip("/"))).replace("\\", "/")
                            for t in v]
                    self.ts_aliases.append((k.rstrip("*"), tgts, os.path.dirname(p)))

    def _try_js(self, base):
        base = os.path.normpath(base).replace("\\", "/")
        if base in self.fileset:
            return base
        stem = re.sub(r"\.(js|jsx|mjs|cjs)$", "", base)
        for e in JS_EXTS:
            if stem + e in self.fileset:
                return stem + e
            if base + e in self.fileset:
                return base + e
        for e in JS_EXTS:
            if base + "/index" + e in self.fileset:
                return base + "/index" + e
        return None

    def js(self, spec, frm):
        if spec.startswith("."):
            return self._try_js(os.path.join(os.path.dirname(frm), spec))
        for prefix, tgts, cfgdir in self.ts_aliases:
            if prefix and spec.startswith(prefix) and frm.startswith(cfgdir):
                rest = spec[len(prefix):]
                for t in tgts:
                    r = self._try_js(os.path.join(t, rest))
                    if r:
                        return r
        # workspace package (e.g. @scope/pkg or @scope/pkg/sub)
        for name, d in self.pkg_names.items():
            if spec == name or spec.startswith(name + "/"):
                sub = spec[len(name):].lstrip("/")
                for cand in ([os.path.join(d, "src", sub), os.path.join(d, sub)] if sub else
                             [os.path.join(d, "src", "index"), os.path.join(d, "index")]):
                    r = self._try_js(cand)
                    if r:
                        return r
                files = self.dir_files.get(d) or self.dir_files.get(d + "/src")
                if files:
                    return files[0]
        return None

    def py(self, spec, frm):
        if spec.startswith("."):
            dots = len(spec) - len(spec.lstrip("."))
            base = os.path.dirname(frm)
            for _ in range(dots - 1):
                base = os.path.dirname(base)
            rest = spec.lstrip(".").replace(".", "/")
            for cand in ([os.path.join(base, rest) + ".py", os.path.join(base, rest, "__init__.py")] if rest
                         else [os.path.join(base, "__init__.py")]):
                cand = os.path.normpath(cand).replace("\\", "/")
                if cand in self.fileset:
                    return cand
            return None
        parts = spec.split(".")
        for i in range(len(parts), 0, -1):
            hit = self.py_index.get(".".join(parts[:i]))
            if hit:
                return hit
        return None

    def php(self, spec):
        for ns, d in sorted(self.psr4.items(), key=lambda kv: -len(kv[0])):
            n = ns.rstrip("\\")
            if spec == n or spec.startswith(n + "\\"):
                rel = spec[len(n):].lstrip("\\").replace("\\", "/")
                cand = (d + "/" + rel + ".php") if rel else d
                if cand in self.fileset:
                    return cand
        return None

    def go(self, spec):
        if not self.go_module:
            return None
        mod, mdir = self.go_module
        if spec == mod or spec.startswith(mod + "/"):
            rel = spec[len(mod):].lstrip("/")
            d = (mdir + "/" + rel).strip("/") if mdir else rel
            fs = [f for f in self.dir_files.get(d, []) if f.endswith(".go")]
            return fs[0] if fs else None
        return None

    def java(self, spec):
        parts = spec.split(".")
        for i in range(len(parts), 1, -1):
            hit = self.java_index.get(".".join(parts[:i]))
            if hit:
                return hit
        return None


def extract_imports(lang, text):
    out = []
    if lang in ("JavaScript", "TypeScript", "Vue", "Svelte"):
        for m in JS_IMPORT.finditer(text):
            s = next((g for g in m.groups() if g), None)
            if s:
                out.append(s)
    elif lang == "Python":
        out += [m.group(1) for m in PY_FROM.finditer(text)]
        out += [m.group(1) for m in PY_IMPORT.finditer(text)]
    elif lang == "PHP":
        out += [m.group(1) for m in PHP_USE.finditer(text)]
    elif lang == "Go":
        for blk in GO_IMPORT_BLOCK.findall(text):
            out += re.findall(r'"([^"]+)"', blk)
        out += GO_IMPORT_ONE.findall(text)
    elif lang in ("Java", "Kotlin"):
        out += [m.group(1) for m in JAVA_IMPORT.finditer(text)]
    return out


# ---------------------------------------------------------------- routes & models
ROUTE_PATTERNS = [
    ("express-like", re.compile(r"""\b(?:app|router|server|api|fastify|route|routes)\.(get|post|put|patch|delete|all)\(\s*['"`]([^'"`]+)['"`]""", re.I)),
    ("nest/decorator", re.compile(r"""@(Get|Post|Put|Patch|Delete)\(\s*['"]([^'"]*)['"]\s*\)""")),
    ("flask/fastapi", re.compile(r"""@\w+\.(get|post|put|patch|delete|route)\(\s*['"]([^'"]+)['"]""")),
    ("django", re.compile(r"""\b(?:re_)?path\(\s*r?['"]([^'"]*)['"]""")),
    ("laravel", re.compile(r"""Route::(get|post|put|patch|delete|resource|apiResource|any)\(\s*['"]([^'"]+)['"]""")),
    ("spring", re.compile(r"""@(Get|Post|Put|Delete|Patch|Request)Mapping\(\s*(?:value\s*=\s*)?["']([^"']*)["']""")),
    ("go", re.compile(r"""\.(Handle|HandleFunc|GET|POST|PUT|DELETE|PATCH)\(\s*"([^"]+)\"""")),
]
MODEL_PATTERNS = [
    ("prisma", re.compile(r"^model\s+(\w+)\s*\{", re.M), (".prisma",)),
    ("sql", re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([\w.]+)[`\"]?", re.I), (".sql",)),
    ("django", re.compile(r"^class\s+(\w+)\((?:[\w.]*\.)?Model\)", re.M), (".py",)),
    ("sqlalchemy", re.compile(r"^class\s+(\w+)\((?:Base|db\.Model|DeclarativeBase)\)", re.M), (".py",)),
    ("sqlmodel", re.compile(r"^class\s+(\w+)\([^)]*table\s*=\s*True[^)]*\)", re.M), (".py",)),
    ("laravel-migration", re.compile(r"Schema::create\(\s*['\"](\w+)['\"]"), (".php",)),
    ("typeorm", re.compile(r"@Entity\([^)]*\)\s*(?:export\s+)?class\s+(\w+)"), (".ts", ".js")),
    ("mongoose", re.compile(r"mongoose\.model\(\s*['\"](\w+)['\"]"), (".ts", ".js")),
    ("sequelize", re.compile(r"sequelize\.define\(\s*['\"](\w+)['\"]|\.init\(\s*\{[^}]*\},\s*\{[^}]*modelName:\s*['\"](\w+)['\"]", re.S), (".ts", ".js")),
    ("jpa", re.compile(r"@Entity[\s\S]{0,200}?class\s+(\w+)"), (".java", ".kt")),
    ("eloquent", re.compile(r"^class\s+(\w+)\s+extends\s+(?:Model|Authenticatable)\b", re.M), (".php",)),
]
ENV_USE = [
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"process\.env\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]\s*\]"),
    re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"os\.environ(?:\.get)?\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]\s*\]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"\benv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"getenv\(\s*['\"]([A-Z][A-Z0-9_]{2,})['\"]"),
    re.compile(r"System\.getenv\(\s*\"([A-Z][A-Z0-9_]{2,})\""),
    re.compile(r"\$\{([A-Z][A-Z0-9_]{2,})(?::-[^}]*)?\}"),
]


def next_routes(p):
    m = re.match(r"^(?:src/)?pages/api/(.+)\.(?:t|j)sx?$", p)
    if m:
        r = "/api/" + re.sub(r"/index$", "", m.group(1))
        return ("ANY", r)
    m = re.match(r"^(?:src/)?app/(.*?)/?route\.(?:t|j)s$", p)
    if m:
        return ("ANY", "/" + m.group(1))
    m = re.match(r"^(?:src/)?app/(.*?)/?page\.(?:t|j)sx?$", p)
    if m:
        return ("PAGE", "/" + m.group(1))
    return None


# ---------------------------------------------------------------- infra
def parse_compose(root, p):
    text = read_text(root, p) or ""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        svcs = {}
        for name, s in ((data or {}).get("services") or {}).items():
            s = s or {}
            dep = s.get("depends_on") or []
            dep = list(dep.keys()) if isinstance(dep, dict) else list(dep)
            env = s.get("environment") or {}
            envk = list(env.keys()) if isinstance(env, dict) else [str(e).split("=")[0] for e in env]
            build = s.get("build")
            svcs[name] = {
                "image": s.get("image"),
                "build": build if isinstance(build, str) else (build or {}).get("context") if build else None,
                "ports": [str(x) for x in (s.get("ports") or [])][:6],
                "depends_on": dep, "env_keys": envk[:20],
            }
        return svcs
    except Exception:
        pass
    svcs, cur, in_services, sub = {}, None, False, None
    for line in text.splitlines():
        if re.match(r"^services:\s*$", line):
            in_services = True
            continue
        if in_services and re.match(r"^\S", line) and not line.startswith("#"):
            in_services = False
        if not in_services:
            continue
        m = re.match(r"^  ([\w.\-]+):\s*$", line)
        if m:
            cur = m.group(1)
            svcs[cur] = {"image": None, "build": None, "ports": [], "depends_on": [], "env_keys": []}
            sub = None
            continue
        if cur:
            m = re.match(r"^    image:\s*(\S+)", line)
            if m:
                svcs[cur]["image"] = m.group(1)
            m = re.match(r"^    build:\s*(\S+)", line)
            if m:
                svcs[cur]["build"] = m.group(1)
            m = re.match(r"^    (ports|depends_on|environment):\s*$", line)
            if m:
                sub = m.group(1)
                continue
            if sub and re.match(r"^      ", line):
                it = line.strip().lstrip("- ").strip().strip("'\"")
                if sub == "ports":
                    svcs[cur]["ports"].append(it)
                elif sub == "depends_on":
                    svcs[cur]["depends_on"].append(it.rstrip(":"))
                elif sub == "environment":
                    svcs[cur]["env_keys"].append(re.split(r"[:=]", it)[0])
            elif re.match(r"^    \S", line):
                sub = None
    return svcs


def scan_infra(root, files, texts_cache):
    infra = {"docker": [], "compose": [], "ci": [], "terraform": [], "kubernetes": [], "other": []}
    for p in files:
        b = os.path.basename(p)
        low = b.lower()
        if low.startswith("dockerfile") or low.endswith(".dockerfile"):
            t = read_text(root, p) or ""
            infra["docker"].append({
                "file": p,
                "base_images": re.findall(r"^FROM\s+(\S+)", t, flags=re.M | re.I)[:4],
                "expose": re.findall(r"^EXPOSE\s+(.+)$", t, flags=re.M | re.I)[:3],
                "cmd": (re.findall(r"^(?:CMD|ENTRYPOINT)\s+(.+)$", t, flags=re.M | re.I) or [None])[-1],
            })
        elif re.match(r"^(docker-)?compose(\.[\w\-]+)?\.ya?ml$", low):
            infra["compose"].append({"file": p, "services": parse_compose(root, p)})
        elif p.startswith(".github/workflows/") and low.endswith((".yml", ".yaml")):
            t = read_text(root, p) or ""
            infra["ci"].append({
                "file": p, "system": "github-actions",
                "name": (re.search(r"^name:\s*(.+)$", t, flags=re.M) or [None, None])[1],
                "triggers": re.findall(r"^\s{2}(push|pull_request|schedule|workflow_dispatch|release):", t, flags=re.M)[:5],
                "run_steps": [r.strip()[:120] for r in re.findall(r"^\s+-?\s*run:\s*(.+)$", t, flags=re.M)[:8]],
            })
        elif low in (".gitlab-ci.yml", "jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml", ".circleci/config.yml") or p == ".circleci/config.yml":
            infra["ci"].append({"file": p, "system": low})
        elif low.endswith(".tf"):
            t = read_text(root, p) or ""
            for m in re.finditer(r'^resource\s+"(\w+)"\s+"(\w+)"', t, flags=re.M):
                if len(infra["terraform"]) < 60:
                    infra["terraform"].append({"file": p, "type": m.group(1), "name": m.group(2)})
        elif low.endswith((".yaml", ".yml")) and re.search(r"(^|/)(k8s|kubernetes|helm|charts|manifests|deploy)(/|$)", p):
            t = read_text(root, p) or ""
            for m in re.finditer(r"^kind:\s*(\w+)\s*$[\s\S]{0,300}?^\s{2}name:\s*([\w.\-]+)", t, flags=re.M):
                if len(infra["kubernetes"]) < 60:
                    infra["kubernetes"].append({"file": p, "kind": m.group(1), "name": m.group(2)})
        elif low in ("vercel.json", "netlify.toml", "serverless.yml", "serverless.yaml", "fly.toml",
                     "render.yaml", "app.yaml", "procfile", "railway.json", "wrangler.toml", "amplify.yml"):
            infra["other"].append({"file": p, "kind": low})
    return infra


def parse_env_examples(root, files, real_env_files=()):
    declared = {}
    for p in real_env_files:  # names only; values never leave this function
        t = read_text(root, p, 200_000) or ""
        for line in t.splitlines():
            m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if m:
                declared.setdefault(m.group(1), {"file": p, "hint": "", "from_real_env_file": True})
    for p in files:
        b = os.path.basename(p).lower()
        is_env_name = b.startswith(".env") or b.endswith(".env") or (
            b.startswith("env.") and b.split(".", 1)[1] in ("example", "sample", "template", "dist", "defaults"))
        if not is_env_name:
            continue
        if is_secret_env_file(p):
            continue
        t = read_text(root, p) or ""
        prev = ""
        for line in t.splitlines():
            s = line.strip()
            if s.startswith("#"):
                prev = s.lstrip("# ").strip()[:140]
                continue
            m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", s)
            if m:
                declared.setdefault(m.group(1), {"file": p, "hint": prev})
                prev = ""
            elif s == "":
                prev = ""
    return declared


def parse_makefile(root, files):
    out = []
    for p in files:
        if os.path.basename(p) in ("Makefile", "makefile", "GNUmakefile"):
            t = read_text(root, p) or ""
            for m in re.finditer(r"^([A-Za-z0-9][\w.\-]*)\s*:(?!=)", t, flags=re.M):
                if m.group(1) not in [x["name"] for x in out if x["file"] == p] and len(out) < 40:
                    out.append({"file": p, "name": m.group(1), "command": "make " + m.group(1)})
    return out


def git_info(root, include_authors):
    info = {}
    if run(["git", "rev-parse", "--git-dir"], root) is None:
        return {"is_git": False}
    info["is_git"] = True
    info["commit"] = (run(["git", "rev-parse", "--short", "HEAD"], root) or "").strip() or None
    info["branch"] = (run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root) or "").strip() or None
    info["last_commit_date"] = (run(["git", "log", "-1", "--format=%cs"], root) or "").strip() or None
    remote = (run(["git", "config", "--get", "remote.origin.url"], root) or "").strip()
    remote = re.sub(r"//[^@/]+@", "//", remote)
    info["remote"] = remote or None
    cnt = (run(["git", "rev-list", "--count", "HEAD"], root) or "").strip()
    info["commit_count"] = int(cnt) if cnt.isdigit() else None
    log = run(["git", "log", "--since=6 months ago", "--name-only", "--pretty=format:", "--no-merges"], root, 30)
    if log and (info["commit_count"] or 0) >= 20:
        c = Counter(l for l in log.splitlines() if l.strip())
        info["hotspots_6mo"] = [{"file": f, "changes": n} for f, n in c.most_common(15)]
    elif log:
        info["hotspots_note"] = "history too short (<20 commits, e.g. shallow clone) for meaningful hotspots"
    if include_authors:
        sl = run(["git", "shortlog", "-sn", "--no-merges", "HEAD"], root, 20)
        if sl:
            info["top_authors"] = [re.sub(r"^\s*\d+\s+", "", l) for l in sl.splitlines()[:5]]
    return info


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--out", default=None, help="output dir (default <repo>/onboarding)")
    ap.add_argument("--max-files", type=int, default=30000)
    ap.add_argument("--include-authors", action="store_true")
    ap.add_argument("--module-threshold", type=int, default=120)
    a = ap.parse_args()

    root = os.path.abspath(a.repo)
    out_dir = os.path.abspath(a.out or os.path.join(root, "onboarding"))
    os.makedirs(out_dir, exist_ok=True)

    out_rel = os.path.relpath(out_dir, root).replace(os.sep, "/")
    files, truncated = list_files(root, a.max_files, None if out_rel.startswith("..") else out_rel)
    env_files_real = [f for f in files if is_secret_env_file(f)]
    files = [f for f in files if ext_of(f) not in BINARY_EXT and not is_secret_env_file(f)]
    lang_files, lang_loc = Counter(), Counter()
    src_texts = {}
    file_loc = {}
    for p in files:
        e = ext_of(p)
        lang = LANG_BY_EXT.get(e)
        if not lang:
            continue
        lang_files[lang] += 1
        if lang in CODE_LANGS or lang in ("YAML", "JSON", "Prisma", "GraphQL", "Terraform", "Markdown", "HTML", "CSS"):
            t = read_text(root, p) if lang in CODE_LANGS or lang in ("Prisma", "GraphQL") else None
            if lang in CODE_LANGS and t is not None:
                n = t.count("\n") + 1
                lang_loc[lang] += n
                file_loc[p] = n
                src_texts[p] = t
            elif t is not None:
                src_texts[p] = t

    mod_of = adaptive_modules([f for f in files], a.module_threshold)
    modules = {}
    for p in files:
        m = mod_of.get(p, "(root)")
        d = modules.setdefault(m, {"id": m, "path": m if m != "(root)" else ".", "files": 0, "loc": 0,
                                   "languages": Counter(), "biggest_files": []})
        d["files"] += 1
        d["loc"] += file_loc.get(p, 0)
        lang = LANG_BY_EXT.get(ext_of(p))
        if lang in CODE_LANGS:
            d["languages"][lang] += 1
        if p in file_loc:
            d["biggest_files"].append((file_loc[p], p))
    mod_list = []
    for m, d in modules.items():
        d["biggest_files"] = [f for _, f in sorted(d["biggest_files"], reverse=True)[:4]]
        d["languages"] = [l for l, _ in d["languages"].most_common(3)]
        d["role_guess"] = role_guess(m)
        mod_list.append(d)
    mod_list.sort(key=lambda d: -d["loc"])

    manifests, deps, frameworks, scripts, pkg_names, psr4, go_module = parse_manifests(root, files)
    scripts += parse_makefile(root, files)

    # import graph
    res = Resolver(root, files, pkg_names, psr4, go_module)
    edge_w, edge_ev = Counter(), defaultdict(list)
    unresolved = Counter()
    langs_with_imports = Counter()
    for p, t in src_texts.items():
        lang = LANG_BY_EXT.get(ext_of(p))
        if lang not in CODE_LANGS:
            continue
        specs = extract_imports(lang, t)
        if specs:
            langs_with_imports[lang] += 1
        for s in specs:
            tgt = None
            if lang in ("JavaScript", "TypeScript", "Vue", "Svelte"):
                tgt = res.js(s, p)
            elif lang == "Python":
                tgt = res.py(s, p)
            elif lang == "PHP":
                tgt = res.php(s)
            elif lang == "Go":
                tgt = res.go(s)
            elif lang in ("Java", "Kotlin"):
                tgt = res.java(s)
            if tgt:
                a_m, b_m = mod_of.get(p), mod_of.get(tgt)
                if a_m and b_m and a_m != b_m:
                    k = (a_m, b_m)
                    edge_w[k] += 1
                    if len(edge_ev[k]) < 3:
                        edge_ev[k].append(f"{p} -> {tgt}")
            elif s.startswith("."):
                unresolved[lang] += 1
    edges = [{"from": k[0], "to": k[1], "weight": w, "examples": edge_ev[k]}
             for k, w in edge_w.most_common(150)]
    unsupported = sorted(l for l in lang_files if l in CODE_LANGS and l not in IMPORT_RESOLVED
                         and l not in ("Shell", "SQL", "PowerShell"))

    # routes / models / env usage
    routes, models, env_used = [], [], defaultdict(list)
    for p, t in src_texts.items():
        e = ext_of(p)
        if LANG_BY_EXT.get(e) in CODE_LANGS or e in (".prisma", ".sql"):
            nr = next_routes(p)
            if nr and len(routes) < 300:
                routes.append({"method": nr[0], "path": nr[1], "file": p, "line": 1, "style": "next-file-routing"})
            if len(routes) < 300 and not re.search(r"(^|/)(tests?|__tests__|spec|e2e|node_modules)(/|$)|\.(test|spec)\.", p):
                for style, rx in ROUTE_PATTERNS:
                    for m in rx.finditer(t):
                        g = [x for x in m.groups() if x is not None]
                        if style == "django":
                            meth, path = "ANY", g[0]
                        else:
                            meth, path = (g[0].upper(), g[1]) if len(g) > 1 else ("ANY", g[0])
                        if style in ("go",) and not path.startswith("/"):
                            continue
                        routes.append({"method": meth, "path": path, "file": p,
                                       "line": t.count("\n", 0, m.start()) + 1, "style": style})
                        if len(routes) >= 300:
                            break
            for style, rx, exts in MODEL_PATTERNS:
                if e in exts and len(models) < 200:
                    for m in rx.finditer(t):
                        name = next((x for x in m.groups() if x), None)
                        if name:
                            models.append({"name": name, "file": p, "style": style})
            if not re.search(r"(^|/)(tests?|__tests__|spec)(/|$)|\.(test|spec)\.", p):
                for rx in ENV_USE:
                    for m in rx.finditer(t):
                        k = m.group(1)
                        if len(env_used[k]) < 2 and p not in env_used[k]:
                            env_used[k].append(p)
    declared = parse_env_examples(root, files, env_files_real)
    infra = scan_infra(root, files, src_texts)

    # service detection: deps + compose images + env keys
    svc_inputs = list(deps)
    for c in infra["compose"]:
        for sname, s in c["services"].items():
            if s.get("image"):
                svc_inputs.append((s["image"].split(":")[0], c["file"]))
    for k, v in list(declared.items()):
        svc_inputs.append((k, v["file"]))
    services = detect_services(svc_inputs)

    # entry points
    entry, seen = [], set()
    ENTRY_RX = re.compile(r"(^|/)(main\.(py|go|ts|js|rs|java|kt)|index\.(ts|js|tsx|jsx)|server\.(ts|js|py)|app\.(py|ts|js)|"
                          r"manage\.py|artisan|wsgi\.py|asgi\.py|Program\.cs|[A-Z]\w*Application\.(java|kt))$")
    for p in files:
        if ENTRY_RX.search(p) and p.count("/") <= 4 and p not in seen:
            if not re.search(r"(node_modules|/tests?/|__tests__|\.d\.ts)", p):
                entry.append({"file": p, "reason": "conventional entry file name"})
                seen.add(p)
    for mf in manifests:
        if isinstance(mf.get("main"), str):
            target = os.path.normpath(os.path.join(os.path.dirname(mf["file"]), mf["main"])).replace("\\", "/")
            if target in set(files) and target not in seen:
                entry.append({"file": target, "reason": f'"main" of {mf["file"]}'})
                seen.add(target)
    entry = entry[:25]

    # tests
    test_files = [p for p in files if re.search(r"(^|/)(tests?|__tests__|spec|e2e)(/|$)|\.(test|spec)\.[a-z]+$|_test\.go$|(^|/)test_[^/]+\.py$", p)]
    test_fw = [f for f in ("Jest", "Vitest", "Mocha", "Cypress", "Playwright", "pytest", "PHPUnit")
               if f in frameworks]
    docs = []
    for p in files:
        if ext_of(p) in (".md", ".mdx", ".rst") and (p.count("/") <= 2 or "docs/" in p or "adr" in p.lower()):
            t = read_text(root, p, 200_000) or ""
            h = re.search(r"^#\s+(.+)$", t, flags=re.M)
            docs.append({"file": p, "title": (h.group(1).strip()[:100] if h else None), "lines": t.count("\n") + 1})
    docs = docs[:60]

    scan = {
        "meta": {"root_name": os.path.basename(root), "file_count": len(files), "truncated": truncated,
                 "tool": "onboarding-atlas/scan.py"},
        "git": git_info(root, a.include_authors),
        "languages": [{"language": l, "files": lang_files[l], "loc": lang_loc.get(l, 0)}
                      for l, _ in sorted(lang_files.items(), key=lambda kv: (-lang_loc.get(kv[0], 0), -kv[1]))
                      if l in CODE_LANGS or lang_files[l] > 3][:14],
        "frameworks": {k: sorted(set(v))[:3] for k, v in frameworks.items()},
        "manifests": manifests,
        "modules": mod_list[:80],
        "module_edges": edges,
        "import_resolution": {
            "resolved_for": sorted(l for l in langs_with_imports if l in IMPORT_RESOLVED),
            "not_resolved_languages": unsupported,
            "unresolved_relative_imports": dict(unresolved),
            "note": "Edges are file-import based and partial. Dynamic imports, DI containers, HTTP/queue calls "
                    "between services are NOT visible here; verify by reading code.",
        },
        "entry_points": entry,
        "routes": routes,
        "data_models": models,
        "services_detected": services,
        "infra": infra,
        "env": {
            "declared": [{"key": k, **v} for k, v in sorted(declared.items())][:150],
            "used_in_code": [{"key": k, "files": v} for k, v in sorted(env_used.items())][:200],
            "used_but_undeclared": sorted(k for k in env_used if k not in declared)[:80],
            "committed_env_files": env_files_real,
        },
        "scripts": scripts[:120],
        "tests": {"file_count": len(test_files), "frameworks": test_fw, "examples": test_files[:8]},
        "docs": docs,
    }
    with open(os.path.join(out_dir, "scan.json"), "w", encoding="utf-8") as f:
        json.dump(scan, f, indent=1, ensure_ascii=False)

    # ----- compact stdout summary
    P = print
    P(f"== onboarding-atlas scan: {scan['meta']['root_name']} ({len(files)} files{', TRUNCATED' if truncated else ''}) ==")
    g = scan["git"]
    if g.get("is_git") and g.get("commit"):
        P(f"git: {g.get('branch')}@{g.get('commit')}  last commit {g.get('last_commit_date')}  commits {g.get('commit_count')}")
    P("languages: " + ", ".join(f"{l['language']} {l['loc']:,}loc" if l["loc"] else f"{l['language']} {l['files']}f"
                                for l in scan["languages"][:8]))
    if frameworks:
        P("frameworks/libs: " + ", ".join(sorted(frameworks)[:20]))
    if services:
        P("services detected: " + ", ".join(s["label"] for s in services[:16]))
    P("\nmodules (top by LOC): id | files | loc | role guess")
    for m in scan["modules"][:18]:
        P(f"  {m['id']} | {m['files']} | {m['loc']:,} | {m['role_guess']}")
    if edges:
        P("\ntop module dependencies (from -> to, #imports):")
        test_mods = {m["id"] for m in scan["modules"] if m["role_guess"] == "test"}
        for e in [e for e in edges if e["from"] not in test_mods][:12]:
            P(f"  {e['from']} -> {e['to']}  ({e['weight']})")
    if entry:
        P("\nentry points: " + ", ".join(e["file"] for e in entry[:8]))
    P(f"routes found: {len(routes)}   data models: {len(models)}   env declared: {len(declared)}   "
      f"env used-but-undeclared: {len(scan['env']['used_but_undeclared'])}")
    if infra["compose"]:
        P("compose services: " + ", ".join(sorted({s for c in infra["compose"] for s in c["services"]})))
    if env_files_real:
        P("WARNING committed env file(s): " + ", ".join(env_files_real) +
          "  -> names were read, values were not; check them for real secrets and tell the user")
    P(f"CI: {len(infra['ci'])} pipeline file(s)   docker: {len(infra['docker'])}   terraform: {len(infra['terraform'])}   "
      f"k8s: {len(infra['kubernetes'])}")
    P(f"tests: {len(test_files)} files {test_fw}")
    if scripts:
        P("scripts: " + ", ".join(f"{s['name']}" for s in scripts[:14]))
    if g.get("hotspots_6mo"):
        P("hotspots (6mo): " + ", ".join(h["file"] for h in g["hotspots_6mo"][:6]))
    ir = scan["import_resolution"]
    P(f"\nimport graph covers: {', '.join(ir['resolved_for']) or 'none'}; NOT covered: "
      f"{', '.join(ir['not_resolved_languages']) or 'none'}")
    P(f"\nwrote {os.path.join(out_dir, 'scan.json')}")


if __name__ == "__main__":
    sys.exit(main())
