#!/usr/bin/env python3
"""onboarding-atlas validator: the gate between "agent wrote it" and "client reads it".

Checks architecture.json and ONBOARDING.md against the real repository:
  * schema sanity (ids, layers, edges, flows)
  * every referenced file/dir exists
  * documented npm/make commands exist
  * documented env vars are declared or used somewhere
  * modules with real code are not silently missing from the diagram
  * no secrets leaked into the generated files

Exit code 1 if any ERROR. Warnings never fail the run but should be read.

Usage:
  python3 validate.py [onboarding_dir] [--repo REPO]
"""
import argparse
import json
import os
import re
import sys

NODE_KINDS = {"ui", "api", "service", "db", "cache", "queue", "external", "job", "library", "infra",
              "storage", "search", "auth", "cli", "docs", "other"}
FILE_EXTS = {
    "js", "jsx", "ts", "tsx", "mjs", "cjs", "py", "php", "java", "kt", "go", "rs", "rb", "cs", "cpp", "c", "h",
    "swift", "dart", "scala", "ex", "sh", "ps1", "sql", "html", "css", "scss", "vue", "svelte", "json", "yml",
    "yaml", "toml", "md", "mdx", "txt", "env", "example", "sample", "lock", "xml", "gradle", "properties", "tf",
    "ini", "cfg", "conf", "prisma", "graphql", "proto", "dockerfile", "wasm", "ipynb", "csv",
}
SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("API key (sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("credentials in URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]{3,}@[^\s/]+")),
    ("inline secret assignment", re.compile(
        r"(?i)\b(password|passwd|secret|api[_-]?key|token|client_secret)\b\s*[:=]\s*['\"]?(?!<|\$|\{|your|xxx|change|example|\.\.\.|\*\*)[A-Za-z0-9/+_\-]{12,}['\"]?")),
]


def exists(repo, ref):
    ref = ref.strip()
    ref = re.sub(r"(:\d+(-\d+)?|#L?\d+.*)$", "", ref)
    ref = ref.rstrip("/")
    if not ref or ref.startswith("/"):
        return False
    return os.path.exists(os.path.join(repo, ref))


def check_architecture(arch, scan, repo):
    errors, warnings = [], []
    refs_total = refs_ok = 0

    def err(m):
        errors.append(m)

    def warn(m):
        warnings.append(m)

    for k in ("project", "nodes", "edges"):
        if k not in arch:
            err(f"architecture.json: missing top-level '{k}'")
    if errors:
        return {"errors": errors, "warnings": warnings, "refs_total": 0, "refs_ok": 0}

    proj = arch["project"]
    if not proj.get("name") or not proj.get("summary"):
        err("project.name and project.summary are required")
    layers = arch.get("layers") or []
    layer_ids = [l.get("id") for l in layers]
    if len(set(layer_ids)) != len(layer_ids):
        err("duplicate layer ids")
    nodes = arch["nodes"]
    ids = [n.get("id") for n in nodes]
    if len(set(ids)) != len(ids):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        err(f"duplicate node ids: {dup}")
    for n in nodes:
        nid = n.get("id", "?")
        if not re.match(r"^[a-z0-9][a-z0-9_\-]*$", str(nid)):
            err(f"node id '{nid}' must be lowercase letters, digits, - or _")
        for req in ("label", "layer", "kind", "description"):
            if not n.get(req):
                err(f"node '{nid}': missing '{req}'")
        if n.get("kind") and n["kind"] not in NODE_KINDS:
            err(f"node '{nid}': kind '{n['kind']}' not in {sorted(NODE_KINDS)}")
        if layer_ids and n.get("layer") not in layer_ids:
            err(f"node '{nid}': layer '{n.get('layer')}' not defined in layers")
        files = n.get("files") or []
        if n.get("kind") not in ("external",) and not files:
            warn(f"node '{nid}': no files listed (every internal component should point at code)")
        for f in files:
            refs_total += 1
            if exists(repo, f):
                refs_ok += 1
            else:
                err(f"node '{nid}': file/dir does not exist: {f}")
        if n.get("confidence") == "low":
            warn(f"node '{nid}': marked low confidence (make sure it is also listed under Open questions)")
        if len(n.get("description", "")) > 600:
            warn(f"node '{nid}': description is long; keep it to 1-3 sentences")
    idset = set(ids)
    connected = set()
    for i, e in enumerate(arch["edges"]):
        a, b = e.get("from"), e.get("to")
        if a not in idset or b not in idset:
            err(f"edge #{i}: unknown endpoint ({a} -> {b})")
            continue
        connected.update((a, b))
        if not e.get("label"):
            warn(f"edge {a} -> {b}: add a short label (what flows/how: 'REST', 'reads/writes', 'enqueues')")
        ev = e.get("evidence") or []
        if not ev:
            warn(f"edge {a} -> {b}: no evidence file listed")
        for f in ev:
            refs_total += 1
            if exists(repo, f):
                refs_ok += 1
            else:
                err(f"edge {a} -> {b}: evidence path does not exist: {f}")
    for n in nodes:
        if n.get("id") not in connected and len(nodes) > 1:
            warn(f"node '{n.get('id')}' has no edges")
    for fl in arch.get("flows") or []:
        if not fl.get("id") or not fl.get("title") or not fl.get("steps"):
            err(f"flow '{fl.get('id', '?')}': needs id, title, steps")
            continue
        for s in fl["steps"]:
            if s.get("node") not in idset:
                err(f"flow '{fl['id']}': step references unknown node '{s.get('node')}'")
            if not s.get("text"):
                err(f"flow '{fl['id']}': step on '{s.get('node')}' has no text")
    if len(nodes) > 45:
        warn(f"{len(nodes)} nodes is too dense for onboarding; group into ~8-25 components")
    if len(nodes) < 3:
        warn("fewer than 3 nodes: diagram will not teach much")

    setup = arch.get("setup") or {}
    scripts = {s["name"] for s in (scan or {}).get("scripts", [])}
    env_known = set()
    if scan:
        env_known = {e["key"] for e in scan["env"]["declared"]} | {e["key"] for e in scan["env"]["used_in_code"]}
    for st in setup.get("steps") or []:
        cmd = st.get("cmd") or ""
        for m in re.finditer(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?([\w:.\-]+)", cmd):
            name = m.group(1)
            builtin = {"install", "i", "ci", "add", "test", "start", "init", "exec", "dlx", "x", "create", "link"}
            if scan and name not in scripts and name not in builtin:
                warn(f"setup step '{st.get('title')}': script '{name}' not found in any package.json")
        for m in re.finditer(r"\bmake\s+([\w.\-]+)", cmd):
            if scan and m.group(1) not in scripts:
                warn(f"setup step '{st.get('title')}': make target '{m.group(1)}' not found")
    for e in setup.get("env") or []:
        if scan and e.get("key") and e["key"] not in env_known:
            warn(f"env var {e['key']} is documented but never declared in .env.example or read in code")

    # coverage: real modules that the diagram never mentions
    if scan:
        covered = [f.rstrip("/") for n in nodes for f in (n.get("files") or [])]
        missing = []
        for m in scan.get("modules", []):
            if m["role_guess"] in ("test", "docs") or m["loc"] < 400:
                continue
            p = m["path"]
            if not any(c == p or c.startswith(p + "/") or p.startswith(c + "/") for c in covered):
                missing.append(f"{p} ({m['files']} files, {m['loc']:,} loc)")
        for x in missing[:8]:
            warn(f"module not represented in diagram: {x}")
    return {"errors": errors, "warnings": warnings, "refs_total": refs_total, "refs_ok": refs_ok}


def looks_like_path(tok):
    if re.search(r"[\s<>{}$*|()=,;'\"!?]|://", tok) or tok.startswith(("/", "http", "~", "@", "-", "#")):
        return False
    t = re.sub(r"(:\d+(-\d+)?|#L?\d+.*)$", "", tok)
    if t.endswith("/") and "/" in t[:-1] + "x":
        return True
    base = t.rsplit("/", 1)[-1]
    if "." not in base:
        return False
    ext = base.rsplit(".", 1)[-1].lower()
    if ext.isdigit() or ext not in FILE_EXTS:
        return False
    if re.match(r"^v?\d+(\.\d+)+$", t):
        return False
    return True


GENERATED_ROOTS = {"node_modules", "dist", "build", "out", "coverage", ".next", ".nuxt", "vendor", "target",
                   "__pycache__", ".venv", "venv", ".gradle", ".turbo", ".cache"}


def check_doc(md_text, repo, scan, out_dir_rel):
    errors, warnings = [], []
    refs = 0
    ok = 0
    ignore = set()
    for m in re.finditer(r"<!--\s*atlas:ignore-paths\s+(.*?)-->", md_text, flags=re.S):
        ignore.update(m.group(1).split())
    for tok in sorted(set(re.findall(r"`([^`\n]+)`", md_text))):
        if not looks_like_path(tok):
            continue
        if out_dir_rel and tok.strip("./").startswith(out_dir_rel.strip("/")):
            continue  # links to the generated outputs themselves
        if tok in ignore or tok.split("/")[0] in GENERATED_ROOTS:
            continue  # declared runtime/generated path
        refs += 1
        if exists(repo, tok):
            ok += 1
        elif tok.endswith("/"):
            warnings.append(f"ONBOARDING.md mentions directory `{tok}` that does not exist in the repo "
                            f"(fine if created at runtime: list it in <!-- atlas:ignore-paths {tok} -->)")
        else:
            errors.append(f"ONBOARDING.md references a path that does not exist: `{tok}` "
                          f"(fix it; if it is created at runtime, list it in <!-- atlas:ignore-paths {tok} -->; "
                          f"if it is not a path, remove the backticks)")
    code_text = "\n".join(re.findall(r"`([^`\n]+)`", md_text) + re.findall(r"```[^\n]*\n(.*?)```", md_text, flags=re.S))
    seen_scripts = set()
    for m in re.finditer(r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?([\w:.\-]+)", code_text):
        name = m.group(1)
        builtin = {"install", "i", "ci", "add", "test", "start", "init", "exec", "dlx", "x", "create", "link", "run", "build"}
        if scan and name not in builtin and name not in seen_scripts and \
                name not in {s["name"] for s in scan.get("scripts", [])}:
            seen_scripts.add(name)
            warnings.append(f"ONBOARDING.md mentions script '{name}' that is not in any package.json")
    for h in ("TL;DR", "Local setup", "Open questions"):
        if not re.search(r"^#+\s.*" + re.escape(h), md_text, flags=re.M | re.I):
            warnings.append(f"ONBOARDING.md has no section matching '{h}'")
    if re.search(r"TODO|TBD|FIXME|<!--\s*fill", md_text):
        warnings.append("ONBOARDING.md still contains TODO/TBD/template placeholders")
    return {"errors": errors, "warnings": warnings, "refs_total": refs, "refs_ok": ok}


def scan_secrets(name, text):
    hits = []
    for label, rx in SECRET_PATTERNS:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{name}:{line}: possible {label} - remove it before sharing")
    return hits


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", nargs="?", default="onboarding")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    out = os.path.abspath(a.out_dir)
    rel = os.path.relpath(out, repo)
    errors, warnings = [], []
    total = good = 0

    scan = None
    t = load(os.path.join(out, "scan.json"))
    if t:
        scan = json.loads(t)
    else:
        warnings.append("scan.json not found: coverage/command/env checks skipped")

    at = load(os.path.join(out, "architecture.json"))
    if at is None:
        errors.append("architecture.json not found")
    else:
        try:
            r = check_architecture(json.loads(at), scan, repo)
            errors += r["errors"]
            warnings += r["warnings"]
            total += r["refs_total"]
            good += r["refs_ok"]
        except json.JSONDecodeError as e:
            errors.append(f"architecture.json is not valid JSON: {e}")

    md = load(os.path.join(out, "ONBOARDING.md"))
    if md is None:
        errors.append("ONBOARDING.md not found")
    else:
        r = check_doc(md, repo, scan, rel)
        errors += r["errors"]
        warnings += r["warnings"]
        total += r["refs_total"]
        good += r["refs_ok"]
        errors += scan_secrets("ONBOARDING.md", md)
    if at:
        errors += scan_secrets("architecture.json", at)
    html = load(os.path.join(out, "architecture.html"))
    if html is None:
        warnings.append("architecture.html not built yet (run build_diagram.py)")

    result = {"errors": errors, "warnings": warnings, "refs_total": total, "refs_ok": good}
    with open(os.path.join(out, "validation.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print(f"validated {good}/{total} file references")
    for e in errors:
        print("ERROR  ", e)
    for w in warnings:
        print("warning", w)
    if errors:
        print(f"\nFAILED: {len(errors)} error(s). Fix them, then run this again.")
        return 1
    print("\nOK" + (f" ({len(warnings)} warning(s) - read them; fix or consciously accept)" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
