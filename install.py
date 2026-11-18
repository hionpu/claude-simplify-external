#!/usr/bin/env python3
"""Install the /simplify-external and /simplify-external-init skills into a Claude Code config directory.

  python install.py                     # $CLAUDE_CONFIG_DIR or ~/.claude
  python install.py --config-dir DIR
  python install.py --force             # replace a skill dir not created by this installer

The skill directory is fully managed (replaced on every install). Per-machine settings
(verified models, exe paths) live outside it in <config-dir>/simplify-external.config.json.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "skills"
MARKER = ".installed-by-claude-simplify-external"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config-dir", help="Claude Code config dir (default: $CLAUDE_CONFIG_DIR or ~/.claude)")
    ap.add_argument("--force", action="store_true", help="replace an existing unmanaged skill dir")
    args = ap.parse_args()

    if sys.version_info < (3, 10):
        print("Python 3.10+ is required", file=sys.stderr)
        return 1
    cfg = Path(args.config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    cfg = cfg.expanduser().resolve()
    if not cfg.is_dir():
        print(f"Claude config dir not found: {cfg}", file=sys.stderr)
        return 1
    if not shutil.which("git"):
        print("git is required on PATH", file=sys.stderr)
        return 1

    names = sorted(p.name for p in SRC.iterdir() if (p / "SKILL.md").is_file())
    targets = {n: cfg / "skills" / n for n in names}
    for dst in targets.values():
        if dst.exists() and not (dst / MARKER).exists() and not args.force:
            print(f"{dst} exists and was not created by this installer; re-run with --force to replace it",
                  file=sys.stderr)
            return 1

    python = Path(sys.executable).resolve().as_posix()
    wrapper = (targets["simplify-external"] / "scripts" / "simplify_external.py").as_posix()
    for name, dst in targets.items():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(SRC / name, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        (dst / MARKER).write_text("managed by install.py; local edits are overwritten\n", encoding="utf-8")
        skill = dst / "SKILL.md"
        text = skill.read_text(encoding="utf-8").replace("{{PYTHON}}", python).replace("{{WRAPPER}}", wrapper)
        skill.write_text(text, encoding="utf-8")
        print(f"installed: {dst}")

    user_cfg = cfg / "simplify-external.config.json"
    print(f"wrapper:   {wrapper}")
    print(f"settings:  {user_cfg} ({'kept' if user_cfg.exists() else 'created by setup'})")
    print("next (once per backend, makes one real model call):")
    print(f'  "{python}" "{wrapper}" setup codex <model-id>')
    print(f'  "{python}" "{wrapper}" setup agy <model-id>')
    print("then restart Claude Code and use: /simplify-external <codex|agy> <--changed|path>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
