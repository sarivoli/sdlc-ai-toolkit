#!/usr/bin/env python3
"""Refresh the vendored awesome-copilot skills/agents.

    python scripts/update_vendor.py --ref main

Re-copies exactly the items listed in vendor/awesome-copilot/SOURCE.md from
github/awesome-copilot at the given ref and updates the pinned commit.
Review the diff and commit it through an MR.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor" / "awesome-copilot"
SKILLS = ["git-commit", "security-review", "pytest-coverage", "refactor", "acquire-codebase-knowledge"]
AGENTS = ["debug", "se-security-reviewer", "critical-thinking"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "ac"
        subprocess.run(["git", "clone", "--filter=blob:none", "--sparse", "https://github.com/github/awesome-copilot.git", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", args.ref], check=True)
        subprocess.run(["git", "-C", str(repo), "sparse-checkout", "set", "skills", "agents"], check=True)
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
        for s in SKILLS:
            src, dst = repo / "skills" / s, VENDOR / "skills" / s
            if not src.exists():
                print(f"WARNING: skill {s} no longer exists upstream; kept old copy", file=sys.stderr)
                continue
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        for a in AGENTS:
            src = repo / "agents" / f"{a}.agent.md"
            if src.exists():
                shutil.copy2(src, VENDOR / "agents" / src.name)
            else:
                print(f"WARNING: agent {a} no longer exists upstream; kept old copy", file=sys.stderr)
        shutil.copy2(repo / "LICENSE", VENDOR / "LICENSE")
    src_md = VENDOR / "SOURCE.md"
    src_md.write_text(re.sub(r"at commit `[0-9a-f]+`", f"at commit `{sha}`", src_md.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Vendored awesome-copilot @ {sha}. Check agent names still match those referenced in agents/*.agent.md.")


if __name__ == "__main__":
    main()
