"""Scenario tests for simplify_external.py using temp git repos, a fake agent CLI and a fake test runner.

Run from the repo root: python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO / "skill" / "scripts" / "simplify_external.py"
REAL_CONFIG = REPO / "skill" / "scripts" / "simplify-external.config.json"
INSTALLER = REPO / "install.py"

FAKE_AGENT = textwrap.dedent(
    r'''
    import json, os, subprocess, sys, time
    from pathlib import Path
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else ""
    counter = Path(os.environ["FAKE_AGENT_COUNTER"])
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    prompt = sys.stdin.read()
    Path(os.environ["FAKE_AGENT_PROMPTS"], f"prompt-{n}.md").write_text(prompt, encoding="utf-8")
    plan = json.loads(Path(os.environ["FAKE_PLAN"]).read_text())
    step = plan[min(n, len(plan)) - 1]
    if not step.get("no_model_header"):
        print("model: " + step.get("report_model", model), flush=True)
    if step.get("print"):
        print(step["print"], flush=True)
    for rel, content in step.get("write", {}).items():
        p = Path(rel); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if step.get("git"):
        subprocess.run(["git", *step["git"]], check=True)
    time.sleep(step.get("sleep", 0))
    sys.exit(step.get("exit", 0))
    '''
)

FAKE_TEST = textwrap.dedent(
    r'''
    import os, sys
    from pathlib import Path
    c = Path(os.environ["FAKE_TEST_COUNTER"])
    c.write_text(str(int(c.read_text()) + 1 if c.exists() else 1))
    src = Path("src/calc.py").read_text(encoding="utf-8")
    noise = int(os.environ.get("FAKE_TEST_NOISE", "0"))
    for i in range(noise):
        print(f"noise line {i} " + "x" * 60)
    if "BASEBROKEN" in src or "BUG" in src:
        print("FAILED tests/test_calc.py::test_add - AssertionError: assert 4 == 3")
        print("E       assert 4 == 3")
        sys.exit(1)
    if "ENVFAIL" in src:
        print("Access is denied.")
        sys.exit(1)
    print("1 passed")
    '''
)

GOOD = "def add(a, b):\n    result = a + b\n    return result\n"
SIMPLE = "def add(a, b):\n    return a + b\n"
BUGGY = "def add(a, b):\n    return a + b + 1  # BUG\n"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="simplify-ext-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        tools = self.tmp / "tools"
        tools.mkdir()
        (tools / "fake_agent.py").write_text(FAKE_AGENT, encoding="utf-8")
        (tools / "fake_test.py").write_text(FAKE_TEST, encoding="utf-8")
        (self.tmp / "prompts").mkdir()
        cfg = json.loads(REAL_CONFIG.read_text(encoding="utf-8"))
        cfg["guide"] = str((REAL_CONFIG.parent / cfg["guide"]).resolve())
        cfg["backends"]["codex"] = {
            "model": "fake-model-1",
            "model_verified": {"how": "test"},
            "argv": [sys.executable, str(tools / "fake_agent.py"), "--model", "{model}"],
            "stdin": "prompt",
            "timeout_sec": 20,
            "preflight": [],
            "model_confirm_regex": "(?m)^model: {model}\\s*$",
            "model_error_patterns": ["model is not supported"],
        }
        self.gcfg_path = self.tmp / "config.json"
        self.gcfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.test_argv = [sys.executable, str(tools / "fake_test.py")]

        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "core.autocrlf", "false")
        self.write("src/calc.py", GOOD)
        self.write("tests/test_calc.py", "def test_add():\n    pass\n")
        self.write_repo_config()
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "init")

        self.env = dict(os.environ)
        self.env.update(
            SIMPLIFY_EXTERNAL_CONFIG=str(self.gcfg_path),
            FAKE_AGENT_COUNTER=str(self.tmp / "agent-count"),
            FAKE_TEST_COUNTER=str(self.tmp / "test-count"),
            FAKE_AGENT_PROMPTS=str(self.tmp / "prompts"),
            FAKE_PLAN=str(self.tmp / "plan.json"),
        )
        self.plan([{"write": {"src/calc.py": SIMPLE}}])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, rel):
        return (self.repo / rel).read_text(encoding="utf-8")

    def write_repo_config(self, **extra):
        cfg = {"verify": [{"name": "unit", "cwd": ".", "argv": self.test_argv, "timeout_sec": 30}]}
        cfg.update(extra)
        self.write(".claude/simplify-external.json", json.dumps(cfg))

    def plan(self, steps):
        (self.tmp / "plan.json").write_text(json.dumps(steps), encoding="utf-8")

    def wrapper(self, *args):
        p = subprocess.run(
            [sys.executable, str(WRAPPER), *args], cwd=self.repo, env=self.env,
            capture_output=True, text=True, encoding="utf-8",
        )
        out = p.stdout
        status = out.splitlines()[0].removeprefix("STATUS: ") if out else ""
        return status, p.returncode, out + p.stderr

    def count(self, name):
        p = self.tmp / f"{name}-count"
        return int(p.read_text()) if p.exists() else 0


class Scenarios(Base):
    def test_green_reuse_skips_baseline(self):
        s, rc, out = self.wrapper("verify-only", "src/calc.py")
        self.assertEqual((s, rc), ("VERIFIED", 0), out)
        self.assertIn("GREEN recorded", out)
        s, rc, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual((s, rc), ("VERIFIED", 0), out)
        self.assertIn("baseline: reused", out)
        self.assertEqual(self.count("agent"), 1)
        self.assertEqual(self.count("test"), 2)  # verify-only + post-edit only

    def test_green_invalidated_by_source_change(self):
        self.wrapper("verify-only", "src/calc.py")
        self.write("src/calc.py", GOOD + "\n# user edit\n")
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "VERIFIED", out)
        self.assertIn("baseline: ran", out)
        self.assertEqual(self.count("test"), 3)

    def test_green_invalidated_by_test_file_and_config_change(self):
        self.wrapper("verify-only", "src/calc.py")
        self.write("tests/test_calc.py", "def test_add():\n    assert True\n")
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertIn("baseline: ran", out)
        self.wrapper("verify-only", "src/calc.py")
        self.write_repo_config(env_inputs=["SOMETHING"])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertIn("baseline: ran", out)

    def test_baseline_failure_does_not_call_agent(self):
        self.write("src/calc.py", GOOD + "# BASEBROKEN\n")
        s, rc, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "BASELINE_FAILED", out)
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.count("agent"), 0)

    def test_first_fix_succeeds(self):
        self.plan([{"write": {"src/calc.py": BUGGY}}, {"write": {"src/calc.py": SIMPLE}}])
        s, rc, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual((s, rc), ("VERIFIED", 0), out)
        self.assertEqual(self.count("agent"), 2)
        fix = (self.tmp / "prompts" / "prompt-2.md").read_text(encoding="utf-8")
        self.assertIn("MINIMAL fix", fix)
        first = (self.tmp / "prompts" / "prompt-1.md").read_text(encoding="utf-8")
        guide = Path(first.split("guide at: ", 1)[1].splitlines()[0])
        self.assertFalse(guide.read_text(encoding="utf-8").startswith("---"))  # front matter stripped
        self.assertIn("AssertionError", fix)
        self.assertNotIn("code simplification guide", fix)

    def test_handoff_after_two_fixes(self):
        self.plan([{"write": {"src/calc.py": BUGGY}}])
        s, rc, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "HANDOFF_REQUIRED", out)
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.count("agent"), 3)
        handoff = Path(next(l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("handoff: ")))
        text = handoff.read_text(encoding="utf-8")
        self.assertIn("AssertionError", text)
        self.assertIn("+    return a + b + 1  # BUG", text)
        self.assertIn("-    result = a + b", text)

    def test_long_log_is_bounded_in_retry_prompt(self):
        self.env["FAKE_TEST_NOISE"] = "500"
        self.plan([{"write": {"src/calc.py": BUGGY}}, {"write": {"src/calc.py": SIMPLE}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "VERIFIED", out)
        fix = (self.tmp / "prompts" / "prompt-2.md").read_text(encoding="utf-8")
        block = fix.split("<<<TEST_OUTPUT\n", 1)[1].split("\nTEST_OUTPUT>>>", 1)[0]
        self.assertLessEqual(len(block.splitlines()), 41)
        self.assertLessEqual(len(block.encode("utf-8")), 4096)
        self.assertIn("AssertionError", block)
        logs = list((self.repo / ".git/simplify-external/runs").glob("*/test-1-1.log"))
        self.assertGreaterEqual(len(logs[0].read_text(encoding="utf-8").splitlines()), 500)

    def test_tail_fallback_is_truncated(self):
        self.env["FAKE_TEST_NOISE"] = "500"
        self.write_repo_config(verify=[{"argv": self.test_argv, "regression_patterns": ["noise line 0 "]}])
        git(self.repo, "commit", "-qam", "cfg")
        # regression pattern hits only first line -> extracted mode; just assert bounds via verify-only
        self.write("src/calc.py", BUGGY)
        s, _, out = self.wrapper("verify-only", "src/calc.py")
        self.assertEqual(s, "TESTS_FAILED", out)
        summary = out.split("failure summary:\n", 1)[1]
        self.assertLessEqual(len(summary.encode("utf-8")), 4096 + 200)

    def test_agent_auth_failure_no_retry(self):
        self.plan([{"print": "ERROR: not logged in", "exit": 1}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "AGENT_FAILED", out)
        self.assertEqual(self.count("agent"), 1)

    def test_denied_action_is_agent_failed_not_no_changes(self):
        cfg = json.loads(self.gcfg_path.read_text(encoding="utf-8"))
        cfg["backends"]["codex"]["incomplete_patterns"] = ['"denied_actions":\\[\\{']
        self.gcfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.plan([{"print": '{"event":"result","result":{"denied_actions":[{"action":"command"}]}}'}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "AGENT_FAILED", out)
        self.assertEqual(self.count("agent"), 1)

    def test_agent_timeout_no_retry(self):
        cfg = json.loads(self.gcfg_path.read_text(encoding="utf-8"))
        cfg["backends"]["codex"]["timeout_sec"] = 2
        self.gcfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        self.plan([{"sleep": 30}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "AGENT_FAILED", out)
        self.assertIn("timed out", out)
        self.assertEqual(self.count("agent"), 1)

    def test_protected_edit_is_violation(self):
        self.plan([{"write": {"tests/test_calc.py": "def test_add():\n    assert 1\n"}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "SCOPE_VIOLATION", out)
        self.assertIn("tests/test_calc.py", out)
        self.assertEqual(self.count("agent"), 1)

    def test_out_of_scope_and_staging_are_violations(self):
        self.write("src/other.py", "X = 1\n")
        git(self.repo, "add", "src/other.py")
        git(self.repo, "commit", "-qm", "other")
        self.plan([{"write": {"src/other.py": "X = 2\n"}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "SCOPE_VIOLATION", out)
        self.assertIn("src/other.py", out)
        self.plan([{"write": {"src/calc.py": SIMPLE}, "git": ["add", "src/calc.py"]}])
        (self.tmp / "agent-count").unlink()
        git(self.repo, "checkout", "-q", "--", "src/other.py")
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "SCOPE_VIOLATION", out)
        self.assertIn("staging", out)

    def test_env_failure_after_edit_is_unverified(self):
        self.plan([{"write": {"src/calc.py": SIMPLE + "# ENVFAIL\n"}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "UNVERIFIED", out)
        self.assertEqual(self.count("agent"), 1)

    def test_user_changes_preserved_and_diff_relative_to_start(self):
        self.write("src/calc.py", GOOD + "# user change\n")
        self.write("notes/untracked.txt", "mine\n")
        self.plan([{"write": {"src/calc.py": SIMPLE + "# user change\n"}}])
        s, _, out = self.wrapper("run", "codex", "--changed")
        self.assertEqual(s, "VERIFIED", out)
        self.assertIn("# user change", self.read("src/calc.py"))
        self.assertEqual(self.read("notes/untracked.txt"), "mine\n")
        diff = Path(next(l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("diff: ")))
        d = diff.read_text(encoding="utf-8")
        self.assertNotIn("+# user change", d)
        self.assertIn("-    result = a + b", d)

    def test_handoff_diff_excludes_preexisting_changes(self):
        self.write("src/calc.py", GOOD + "# user change\n")
        self.plan([{"write": {"src/calc.py": BUGGY + "# user change\n"}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "HANDOFF_REQUIRED", out)
        handoff = next(l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("handoff: "))
        text = Path(handoff).read_text(encoding="utf-8")
        self.assertNotIn("+# user change", text)

    def test_path_with_spaces(self):
        self.write("my src/a b.py", "def f():\n    x = 1\n    return x\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "space")
        self.plan([{"write": {"my src/a b.py": "def f():\n    return 1\n"}}])
        s, _, out = self.wrapper("run", "codex", "my src")
        self.assertEqual(s, "VERIFIED", out)
        self.assertIn("my src/a b.py", out)

    def test_rejects_bad_input(self):
        outside = self.tmp / "outside.py"
        outside.write_text("x=1\n")
        for args in (
            ("run", "codex", "../outside.py"),
            ("run", "codex", str(outside)),
            ("run", "gemini", "src/calc.py"),
            ("run", "codex", "src/calc.py", "--extra"),
            ("run", "codex", "--yolo"),
            ("run", "codex", ".git/config"),
        ):
            s, rc, out = self.wrapper(*args)
            self.assertEqual((s, rc), ("INVALID_INPUT", 2), f"{args}: {out}")
        self.assertEqual(self.count("agent"), 0)

    def test_empty_changed_scope(self):
        s, rc, out = self.wrapper("run", "codex", "--changed")
        self.assertEqual(s, "EMPTY_SCOPE", out)
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.count("agent"), 0)

    def test_missing_repo_config(self):
        (self.repo / ".claude/simplify-external.json").unlink()
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.assertIn("never guessed", out)

    def test_lock_blocks_concurrent_run(self):
        lock = self.repo / ".git/simplify-external/lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("123")
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "LOCKED", out)
        self.assertEqual(self.count("agent"), 0)

    def test_no_changes(self):
        self.plan([{}])
        s, rc, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual((s, rc), ("NO_CHANGES", 0), out)


class ModelPolicy(Base):
    def test_same_model_passed_on_every_call(self):
        self.plan([{"write": {"src/calc.py": BUGGY}}])
        self.wrapper("run", "codex", "src/calc.py")
        logs = sorted((self.repo / ".git/simplify-external/runs").glob("*/agent-*.log"))
        self.assertEqual(len(logs), 3)
        for log in logs:
            self.assertIn('"--model", "fake-model-1"', log.read_text(encoding="utf-8"))

    def test_unconfirmed_model_stops(self):
        self.plan([{"no_model_header": True, "write": {"src/calc.py": SIMPLE}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.assertIn("could not confirm", out)
        self.assertEqual(self.count("test"), 1)  # baseline only; no post-edit judging

    def test_fallback_model_reported_stops(self):
        self.plan([{"report_model": "other-model", "write": {"src/calc.py": SIMPLE}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)

    def test_rejected_model_stops_without_retry(self):
        self.plan([{"print": "ERROR: The 'x' model is not supported", "exit": 1}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.assertEqual(self.count("agent"), 1)

    def test_unverified_or_missing_model_refuses_before_any_call(self):
        cfg = json.loads(self.gcfg_path.read_text(encoding="utf-8"))
        cfg["backends"]["codex"]["model_verified"] = None
        self.gcfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)
        cfg["backends"]["codex"]["model_verified"] = {"how": "t"}
        cfg["backends"]["codex"]["argv"] = [a for a in cfg["backends"]["codex"]["argv"] if a not in ("--model", "{model}")]
        self.gcfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.assertEqual(self.count("agent") + self.count("test"), 0)

    def test_agy_unconfigured_is_config_error(self):
        cfg = json.loads(self.gcfg_path.read_text(encoding="utf-8"))
        cfg["backends"]["agy"] = {"model": None, "argv": None, "note": "test"}
        self.gcfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        s, _, out = self.wrapper("run", "agy", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.assertEqual(self.count("agent"), 0)


class Setup(Base):
    def use_fake_backend_without_model(self):
        cfg = json.loads(self.gcfg_path.read_text(encoding="utf-8"))
        cfg["backends"]["codex"].update(model=None, model_verified=None, version_args=["-c", "print('fake 1.0')"])
        self.gcfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    def test_run_refuses_until_setup(self):
        self.use_fake_backend_without_model()
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.assertEqual(self.count("agent"), 0)

    def test_setup_records_verified_model_then_run_works(self):
        self.use_fake_backend_without_model()
        self.plan([{}])
        s, rc, out = self.wrapper("setup", "codex", "fake-model-2")
        self.assertEqual((s, rc), ("CONFIGURED", 0), out)
        saved = json.loads(self.gcfg_path.read_text(encoding="utf-8"))["backends"]["codex"]
        self.assertEqual(saved["model"], "fake-model-2")
        self.assertIn("fake 1.0", saved["model_verified"]["cli"])
        self.plan([{"write": {"src/calc.py": SIMPLE}}])
        s, _, out = self.wrapper("run", "codex", "src/calc.py")
        self.assertEqual(s, "VERIFIED", out)
        logs = sorted((self.repo / ".git/simplify-external/runs").glob("*/agent-1.log"))
        self.assertIn('"--model", "fake-model-2"', logs[-1].read_text(encoding="utf-8"))

    def test_setup_rejects_unconfirmed_or_rejected_model(self):
        self.use_fake_backend_without_model()
        self.plan([{"report_model": "default-model"}])
        s, _, out = self.wrapper("setup", "codex", "fake-model-2")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.plan([{"print": "ERROR: model is not supported", "exit": 1}])
        s, _, out = self.wrapper("setup", "codex", "fake-model-2")
        self.assertEqual(s, "CONFIG_ERROR", out)
        self.assertIsNone(json.loads(self.gcfg_path.read_text(encoding="utf-8"))["backends"]["codex"]["model"])

    def test_setup_rejects_bad_model_id(self):
        s, rc, out = self.wrapper("setup", "codex", "--dangerous")
        self.assertEqual((s, rc), ("INVALID_INPUT", 2), out)


class Install(unittest.TestCase):
    def test_install_renders_paths_and_protects_unmanaged_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp)
            p = subprocess.run([sys.executable, str(INSTALLER), "--config-dir", tmp], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            skill = (cfg / "skills/simplify-external/SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("{{", skill)
            self.assertIn((cfg / "skills/simplify-external/scripts/simplify_external.py").resolve().as_posix(), skill)
            # reinstall over a managed dir is fine
            p = subprocess.run([sys.executable, str(INSTALLER), "--config-dir", tmp], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            # an unmanaged dir is not replaced without --force
            (cfg / "skills/simplify-external/.installed-by-claude-simplify-external").unlink()
            p = subprocess.run([sys.executable, str(INSTALLER), "--config-dir", tmp], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
