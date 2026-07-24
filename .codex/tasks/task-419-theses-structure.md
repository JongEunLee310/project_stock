# Codex Handoff Task

## Source Issue

#419 — BE: theses 도메인 구조 통일 — conflict_* prefix를 conflicts/ 서브디렉터리로 이동

## Task Summary

`theses` 도메인의 `conflict_*` 파일 prefix 분리를 `signals/rules/`와 동일한 서브디렉터리 방식(`theses/conflicts/`)으로 통일한다. 순수 구조 이동이며 런타임 동작·계약은 불변이다.

## Goal

완료 시 다음이 참이어야 한다.

- `app/domains/theses/conflict_{model,repository,schema,service}.py` 4개 파일이 `app/domains/theses/conflicts/` 디렉터리로 이동한다.
- 이동 후 파일명에서 `conflict_` prefix를 제거한다(`conflicts/model.py`, `conflicts/repository.py`, `conflicts/schema.py`, `conflicts/service.py`).
- `app/domains/theses/conflicts/__init__.py`가 존재한다.
- 모든 참조처의 import 경로가 새 위치를 가리키고, 전체 테스트가 통과한다.

## Background

- `signals` 도메인은 하위 규칙을 `app/domains/signals/rules/` 서브디렉터리로 둔다. `theses`는 같은 성격의 하위 구성요소(thesis conflict 분석)를 `conflict_*` 파일 prefix로 두고 있어 컨벤션이 갈린다.
- 외부 참조처 5개(app): `app/domains/analysis/service.py`, `app/domains/signals/rules/base.py`, `app/adapters/llm/prompts/thesis_conflict.py`, `app/db/models.py`(모델 등록 side-effect import).
- 외부 참조처 4개(tests): `tests/test_rule_engine.py`, `tests/test_thesis_conflict.py`, `tests/test_llm_factory.py`.
- 내부 상호 참조: `conflict_service.py`와 `conflict_repository.py`가 서로를 import한다. 이동 시 내부 import 경로도 갱신해야 한다.
- `app/db/models.py:23`은 `import app.domains.theses.conflict_model`을 side-effect(모델 등록)로 사용한다. 이 경로가 새 위치를 가리키도록 반드시 갱신한다.

## Implementation Scope

- 위 4개 파일을 `app/domains/theses/conflicts/`로 이동하고 `conflict_` prefix 제거.
- `app/domains/theses/conflicts/__init__.py` 추가(`theses/__init__.py`의 기존 스타일을 따른다).
- 이동한 파일들의 내부 상호 import 경로 갱신.
- 외부 참조처 9개(app 5 + tests 4)의 import 경로 갱신.
- 파일 이동은 `git mv`로 수행해 이력을 보존한다.

## Out of Scope

- 클래스·함수·시그니처·쿼리·비즈니스 로직 변경 금지. 순수 이동과 import 갱신만.
- `theses`의 비-conflict 파일(`model.py`, `repository.py`, `schema.py`, `service.py`)은 건드리지 않는다.
- 컨벤션 문서화(별도 이슈 #420)는 이 작업에 포함하지 않는다.

## Protected Files

없음. `app/db/models.py`는 protected가 아니며, 등록 import 라인 갱신만 허용된다.

## Requirements

- 이동 후 심볼(클래스명 등)은 그대로 유지한다. import 경로만 바뀐다.
- 이동한 파일에 남은 `conflict_` 접두 참조가 없어야 한다.

## Test Requirements

- 테스트 파일의 import 경로 갱신 외에 테스트 로직·기대값 변경 금지.
- 기존 테스트(`test_thesis_conflict.py`, `test_rule_engine.py`, `test_llm_factory.py`)가 이동 후 그대로 통과해야 한다.

## Verification Commands

```
uv run ruff check .
uv run mypy app
uv run pytest
grep -rn "theses.conflict_\|theses import conflict_" app tests
```

마지막 grep은 잔여 참조가 없어 출력이 비어야 한다.

## Documentation Impact

이 PR에서는 코드 이동만 수행한다. 컨벤션 서술(서브디렉터리 규약)은 #420에서 다룬다. ADR·Failure Record 불필요.

## ADR Need

불필요. 아키텍처 결정이 아니라 기존 `signals/rules/` 컨벤션에 맞춘 구조 정렬이다.

## Failure Record Need

불필요. 장애 대응이 아니다.

## Risk Level

Low — 순수 파일 이동과 import 갱신. 로직 무변경, 테스트로 회귀 검출 가능.

## Expected Output

- `git mv` 기반 파일 이동과 9개 참조처 import 갱신 diff.
- `dev`를 타깃으로 하는 PR에 이 핸드오프 문서와 함께 포함될 구현.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
