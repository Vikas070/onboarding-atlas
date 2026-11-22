#!/usr/bin/env python3
"""Build the interactive architecture page.

Reads architecture.json (written by the agent) and optionally scan.json, validates
the references, and writes ONE self-contained HTML file (no CDN, works offline,
safe to email to a client).

Usage:
  python3 build_diagram.py onboarding/architecture.json [--scan onboarding/scan.json]
         [--repo .] [--out onboarding/architecture.html] [--repo-url https://github.com/org/repo]
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate  # noqa: E402


def derive_repo_url(remote):
    """git@github.com:org/repo.git | https://host/org/repo.git -> https://host/org/repo (known hosts only)."""
    if not remote:
        return None
    import re
    m = re.match(r"^(?:git@|ssh://git@|https?://)(github\.com|gitlab\.com|bitbucket\.org)[:/](.+?)(?:\.git)?/?$", remote)
    return f"https://{m.group(1)}/{m.group(2)}" if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("architecture")
    ap.add_argument("--scan")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out")
    ap.add_argument("--repo-url", help="e.g. https://github.com/org/repo : makes file paths clickable")
    ap.add_argument("--branch", default=None)
    a = ap.parse_args()

    with open(a.architecture, encoding="utf-8") as f:
        arch = json.load(f)
    scan = None
    sp = a.scan or os.path.join(os.path.dirname(a.architecture), "scan.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            scan = json.load(f)

    repo = os.path.abspath(a.repo)
    res = validate.check_architecture(arch, scan, repo)
    for e in res["errors"]:
        print("ERROR  ", e)
    for w in res["warnings"]:
        print("warning", w)
    if res["errors"]:
        print(f"\nNot built: {len(res['errors'])} error(s) in architecture.json. Fix and re-run.")
        return 1

    git = (scan or {}).get("git", {})
    data = {
        "arch": arch,
        "meta": {
            "generated": datetime.date.today().isoformat(),
            "commit": git.get("commit"),
            "branch": a.branch or git.get("branch"),
            "refs_ok": res["refs_ok"], "refs_total": res["refs_total"],
            "repo_url": (a.repo_url or derive_repo_url(git.get("remote")) or "").rstrip("/") or None,
        },
    }
    if scan:
        data["scan"] = {
            "languages": scan.get("languages", [])[:8],
            "modules": [{k: m[k] for k in ("id", "path", "files", "loc", "languages", "role_guess")}
                        for m in scan.get("modules", [])[:40]],
            "hotspots": (scan.get("git") or {}).get("hotspots_6mo", [])[:10],
            "routes": [{"method": r["method"], "path": r["path"], "file": r["file"]} for r in scan.get("routes", [])[:60]],
            "models": [{"name": m["name"], "file": m["file"]} for m in scan.get("data_models", [])[:60]],
            "env": [{"key": e["key"], "hint": e.get("hint", ""), "file": e["file"]} for e in scan["env"]["declared"][:80]],
        }

    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "diagram.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    html = tpl.replace("/*__ATLAS_DATA__*/null", blob)
    title = (arch.get("project") or {}).get("name", "Architecture")
    html = html.replace("__ATLAS_TITLE__", title.replace("<", "&lt;"))
    out = a.out or os.path.join(os.path.dirname(a.architecture), "architecture.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"built {out} ({len(html)//1024} KB, {len(arch['nodes'])} nodes, {len(arch['edges'])} edges, "
          f"{res['refs_ok']}/{res['refs_total']} refs verified, {len(res['warnings'])} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
