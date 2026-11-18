---
name: simplify-external
description: Delegate scoped code simplification to an external CLI agent (codex or agy) and run independent regression verification.
disable-model-invocation: true
argument-hint: "<codex|agy> <--changed|repo-relative-path>"
---

입력: $ARGUMENTS

백엔드 하나와 대상 하나만 받는다. 공백이 있는 경로는 인용된 하나의
인자로 처리한다. 백엔드는 codex 또는 agy여야 한다. 그 외 형태면 실행하지
말고 사용법만 알린다.

대상 저장소 루트에서 아래를 한 번 실행하고 종료를 기다린다(타임아웃은
최대값 사용). 검증된 백엔드와 대상만 별도 인자로 전달한다. 원본 입력 전체를
셸 명령에 붙이거나 셸 식으로 평가하지 않는다. 출력이 지연되거나 백그라운드로
전환되어도 중복 실행하지 않는다.

    "{{PYTHON}}" "{{WRAPPER}}" run BACKEND "SCOPE"

출력 첫 줄 `STATUS: <상태>`로 분기한다.

- VERIFIED 또는 NO_CHANGES: 한 줄로 결과만 보고한다.
- HANDOFF_REQUIRED: 출력의 `handoff:` 파일(마지막 실패 요약과 작업 시작
  대비 변경분)을 읽고 원인과 최소 수정안을 제시한다. 직접 편집하거나 외부
  에이전트를 다시 호출하지 않는다. 전체 로그는 요약만으로 진단이 어려울 때만
  읽는다.
- 그 외 상태: 상태, 원인, 필요한 로그 경로만 보고한다.

사용자가 이후 수정을 지시했다면 같은 범위로
`"{{PYTHON}}" "{{WRAPPER}}" verify-only "SCOPE"`를 실행해 재검증한다.

## 설정 (사람이 확인)

- 백엔드 모델: 머신마다 한 번 `"{{PYTHON}}" "{{WRAPPER}}" setup <codex|agy> <model-id>`.
  실제 비대화형 호출로 모델을 확인한 뒤에만 기록한다. 기록이 없으면 run은 CONFIG_ERROR.
- 저장소 테스트: 대상 저장소의 `.claude/simplify-external.json`. 없으면 CONFIG_ERROR를
  보고만 한다. 직접 만들지 않는다. 생성은 사용자가 `/simplify-external-init`을 호출해서 한다.
