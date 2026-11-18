# claude-simplify-external

A Claude Code skill, `/simplify-external`, that hands scoped code simplification to an
external CLI agent (OpenAI Codex CLI or Google Antigravity `agy`) and then verifies the
result with **your repository's own tests**, run by a fixed wrapper. Claude does not edit the
code. It only diagnoses the result if the regression loop runs out of attempts.

```text
/simplify-external codex --changed
/simplify-external codex src/inventory/InventoryService.cs
/simplify-external agy "src/my folder/"
```

## How it works

```text
run(backend, scope)
  preflight ??fix scope file list + verification set
  reuse a matching GREEN record, or run the baseline tests (fail ??BASELINE_FAILED, no agent call)
  snapshot the work tree
  1 simplification call + at most 2 regression-fix calls (same backend, same model):
    agent edits ??scope check ??wrapper runs the tests itself
    pass ??VERIFIED / NO_CHANGES
    code regression ??fix prompt with a bounded failure summary (??0 lines / 4 KiB)
    still failing after 3 calls ??HANDOFF_REQUIRED (handoff.md: last failure + diff since run start)
    scope violation / agent or environment failure ??separate status, no retry
```

- **Scope**: `--changed` = staged, unstaged and untracked (not ignored) files; or one repo-relative
  file/folder. Tests, CI and test config, dependency/lock files, agent config (`.claude/`, `AGENTS.md`, ??
  are never editable. Deleted, binary and symlinked files are skipped.
- **Post-check** (detection, not a sandbox): any new change outside the allowed files, staging,
  commits or branch switches ??`SCOPE_VIOLATION`. Pre-existing user changes are not flagged and
  are never reverted. Nothing is rolled back automatically.
- **GREEN reuse**: `verify-only <scope>` records a passing run with a fingerprint of HEAD, every
  dirty/untracked file's content, declared extra inputs, environment identity, test commands and
  config. `run` skips the baseline only when the fingerprint still matches.
- **Failure classification**: timeouts, missing executables and known environment patterns never
  consume fix attempts. Only failures matching test/compile patterns count as regressions.
  A non-zero exit code alone is not treated as a regression.
- **Models**: each backend uses one model, verified once per machine by `setup` with a real
  non-interactive call. Every run passes it explicitly and confirms it from the CLI output
  (Codex header `model: ??, agy stream-json `init.model`). If the model can't be confirmed or is
  rejected, the run stops with `CONFIG_ERROR`. There is no silent fallback.
- State and logs live in `<git-dir>/simplify-external/`, outside the work tree.

| Status | Meaning | Exit |
|---|---|---|
| `VERIFIED` | net change, final independent tests pass | 0 |
| `NO_CHANGES` | no net change, tests pass | 0 |
| `BASELINE_FAILED` | tests fail before any edit; agent not called | 10 |
| `HANDOFF_REQUIRED` | regression remains after 1 + 2 calls | 11 |
| `SCOPE_VIOLATION` | out-of-scope/protected change, staging or commit | 12 |
| `AGENT_FAILED` | agent CLI failed, timed out, or stopped after a denied action | 13 |
| `UNVERIFIED` | tests could not judge (environment, unknown failure, inputs changed mid-test) | 14 |
| `EMPTY_SCOPE`, `LOCKED`, `CONFIG_ERROR`, `INVALID_INPUT` | see message | 15, 16, 17, 2 |

## Install (once per machine)

Requirements: Python 3.10+, git, Claude Code, and at least one of `codex` / `agy` installed and signed in.

```sh
git clone https://github.com/hionpu/claude-simplify-external
cd claude-simplify-external
python install.py                 # installs into $CLAUDE_CONFIG_DIR or ~/.claude
# or: python install.py --config-dir /path/to/claude/config
```

Then verify each backend's model once (one real model call each). Use exact CLI model IDs
(`agy models`, Codex `~/.codex/models_cache.json` or `codex` model picker):

```sh
python <config-dir>/skills/simplify-external/scripts/simplify_external.py setup codex <model-id>
python <config-dir>/skills/simplify-external/scripts/simplify_external.py setup agy <model-id>
```

`setup` writes `<config-dir>/simplify-external.config.json` (model, exe path, verification record).
Restart Claude Code. To update: `git pull && python install.py`. Your settings are kept.

## Per-repository test configuration (required)

The wrapper never guesses test commands. Each target repo needs `.claude/simplify-external.json`
with commands confirmed from CI or project scripts. Without it, `run` stops with `CONFIG_ERROR` and
points to **`/simplify-external-init`**. That is a separate skill you invoke yourself, once per
repository. It gathers evidence (CI, scripts, docs), proposes the file with sources for your
approval, writes it, and runs `verify-only .` once. Like `/simplify-external` it uses
`disable-model-invocation: true`, so it is never loaded unless you call it. Format:

```json
{
  "verify": [
    {"name": "unit", "cwd": ".", "argv": ["dotnet", "test", "My.sln"], "timeout_sec": 900},
    {"name": "web", "paths": ["web/"], "cwd": "web", "argv": ["npm", "test"]}
  ],
  "protected": ["src/Generated/"],
  "extra_inputs": [".env.test"],
  "env_inputs": ["MY_TEST_FLAG"],
  "reuse_baseline": true
}
```

- An entry without `paths` is the default. An entry with `paths` applies to those prefixes, and the
  longest prefix wins. A scope spanning several packages runs the deduplicated union.
- `argv` is an argument array, never a shell string.
- Optional `regression_patterns` / `env_failure_patterns` per entry extend the built-in patterns.
- Build output that tests create (`__pycache__/`, `bin/`, `obj/`, ?? must be git-ignored.
  Otherwise test inputs appear to change during the run and the result is `UNVERIFIED`.

## TDD integration

If a task will be followed by `/simplify-external`, do its final GREEN check with
`simplify_external.py verify-only <scope>` instead of running the same tests twice. `run` then
reuses that record. Narrow unit tests during development are fine but are not the baseline.

## Development

```sh
python -m unittest discover -s tests -v   # fake agent CLI + fake test runner in temp repos
```

## License

MIT for this project (see `LICENSE`). `skills/simplify-external/code-simplifier.md` and the derived
`skills/simplify-external/code-simplifier.body.md` come from Anthropic's `code-simplifier` plugin and are licensed
under Apache License 2.0 (`skills/simplify-external/LICENSE-code-simplifier`). Provenance and the modification
(front matter removed) are recorded in `skills/simplify-external/SOURCE.md`.
