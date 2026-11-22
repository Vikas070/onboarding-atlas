"""The scan must never open a real .env file. Run: python3 tests/test_scan_never_reads_env.py"""
import builtins, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SENTINEL = "SENTINEL_SECRET_VALUE_12345"


def main():
    repo = Path(tempfile.mkdtemp())
    (repo / "app.js").write_text("const k = process.env.API_KEY;\n")
    (repo / ".env").write_text(f"API_KEY={SENTINEL}\n")
    (repo / ".env.production").write_text(f"DB_PASS={SENTINEL}\n")
    (repo / ".env.example").write_text("API_KEY=changeme\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    spec = importlib.util.spec_from_file_location("scan", ROOT / "scripts" / "scan.py")
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    opened = []
    real_open = builtins.open
    builtins.open = lambda f, *a, **k: (opened.append(str(f)), real_open(f, *a, **k))[1]
    try:
        sys.argv = ["scan.py", str(repo), "--out", str(repo / "out")]
        scan.main()
    finally:
        builtins.open = real_open
    bad = [p for p in opened if os.path.basename(p) in (".env", ".env.production")]
    assert not bad, f"scan opened real env files: {bad}"
    out = (repo / "out" / "scan.json").read_text()
    assert SENTINEL not in out
    data = json.loads(out)
    assert ".env" in data["env"].get("committed_env_files", []) or ".env" in out
    assert "API_KEY" in out  # still learned from .env.example / code usage
    print("OK: real .env files were not opened; no secret value in scan.json")


if __name__ == "__main__":
    main()
