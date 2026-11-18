---
name: simplify-external-init
description: One-time setup of a repository's test configuration (.claude/simplify-external.json) for /simplify-external.
disable-model-invocation: true
argument-hint: "(no arguments; run inside the target repository)"
---

현재 저장소에 `/simplify-external`용 테스트 설정 `.claude/simplify-external.json`을 만든다.
사용자가 이 스킬을 직접 호출했을 때만 수행한다. 테스트 명령은 근거로만 정하고 추측하지 않는다.

## 1. 확인

- `git rev-parse --show-toplevel`로 저장소 루트를 확인한다. 저장소가 아니면 중단한다.
- 설정 파일이 이미 있으면 내용을 보여주고, 사용자가 다시 만들라고 하기 전에는 중단한다.

## 2. 근거 수집 (읽기만)

필요한 것만 읽는다. 많이 읽을 필요는 없다.

- CI: `.github/workflows/*`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `.circleci/`, `Jenkinsfile` 등의 test 단계
- 스크립트: `package.json` scripts, `Makefile`/`justfile`, `pyproject.toml`/`tox.ini`/`noxfile.py`,
  `*.sln`/테스트 프로젝트, `Cargo.toml`, `go.mod`, Unity 테스트 러너 설정 등
- 문서: `README`, `CONTRIBUTING`, `CLAUDE.md`, `AGENTS.md`의 테스트 실행법
- 대상별로 명령이 다른지 확인한다(모노레포, 패키지별 테스트).

근거가 서로 다르거나, 필요한 런타임·도구가 이 PC에 없으면(`where`/`which`로 확인) 추측하지 말고
해결할 항목을 보고한 뒤 중단한다.

## 3. 초안 제시 후 승인 대기

아래 형식으로 초안을 만들고, 항목마다 근거(파일:줄)를 붙여 보여준다. 승인 전에는 파일을 쓰지 않는다.

```json
{
  "verify": [
    {"name": "unit", "cwd": ".", "argv": ["dotnet", "test", "My.sln"], "timeout_sec": 900},
    {"name": "web", "paths": ["web/"], "cwd": "web", "argv": ["npm", "test"]}
  ],
  "protected": [],
  "extra_inputs": [],
  "env_inputs": [],
  "reuse_baseline": true
}
```

- `verify`: `argv`는 인자 배열이다(셸 문자열, 파이프, `&&` 금지). 셸 기능이 꼭 필요하면 저장소에
  이미 있는 스크립트를 호출한다. `cwd`는 저장소 기준 상대 경로다.
- `paths`가 없는 항목은 기본 검증이다. `paths`가 있으면 그 접두사에만 적용되고, 가장 긴 접두사가
  우선한다. 기본 항목이 없으면 어떤 항목에도 속하지 않는 파일은 CONFIG_ERROR가 된다.
- CI 전체 파이프라인이 아니라, 동작 회귀를 잡는 가장 좁고 빠른 테스트 명령을 고른다. 빌드가
  필요하면 테스트 명령이 빌드를 포함하는지 확인한다.
- `timeout_sec`: 기본 900. 느린 스위트는 근거에 맞게 늘린다.
- `protected`: 전역 기본값(테스트·CI·의존성·에이전트 설정) 외에 이 저장소에서 편집하면 안 되는
  경로를 추가한다. 예: 생성 코드, 벤더 코드, 마이그레이션, 공개 API 스냅샷.
- `extra_inputs`: 테스트에 영향을 주는 git 무시 파일(예: `.env.test`). 없으면 비운다.
- `env_inputs`: 테스트 결과를 바꾸는 환경 변수 이름. 값은 기록하지 않는다.
- `reuse_baseline`: 환경이나 외부 입력(DB, 네트워크 등)을 믿을 수 있게 비교하지 못하면 false로 둔다.
- 필요할 때만 항목별 `regression_patterns`, `env_failure_patterns`(정규식)를 추가한다. 기본 패턴은
  dotnet, pytest, jest/vitest, go, cargo, tsc의 일반적인 실패 출력을 다룬다.

## 4. 작성과 확인

승인받으면 `.claude/simplify-external.json`을 쓴 뒤 저장소 루트에서 한 번 실행한다.

    "{{PYTHON}}" "{{WRAPPER}}" verify-only .

- `VERIFIED`: 설정 완료로 보고하고, 이 파일을 저장소에 커밋할지 사용자에게 묻는다(직접 커밋하지 않는다).
- `UNVERIFIED`이고 "inputs changed during the run"이면: 테스트가 만드는 산출물(`bin/`, `obj/`,
  `__pycache__/`, `coverage/` 등)이 git에서 무시되지 않는 경우다. 추가할 `.gitignore` 항목을
  제안하고, 승인받은 뒤 반영해 다시 실행한다.
- `TESTS_FAILED`: 현재 코드가 실패하는 상태다. 설정 문제가 아니므로 실패 요약만 보고한다.
- 그 외: 상태와 원인을 보고하고, 설정을 고칠지 묻는다.
