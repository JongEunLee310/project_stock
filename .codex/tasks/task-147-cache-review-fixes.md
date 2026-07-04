# Codex Handoff Task

## Source Issue

- BE #138 — LLM Cache 구현(task-146)에 대한 블라인드 코드 리뷰 적발 사항 반영
- 설계: `docs/designs/080-llm-response-cache.md` (Decisions III·JJJ·KKK)
- 선행: task-146 완료 상태의 `experiment/138-llm-cache-fable` 브랜치에서 이어 실행한다.

## Task Summary

리뷰에서 적발된 4건을 수정한다. (1) 빈 output이 정상 결과로 캐싱되어 TTL 동안
고착되는 경로 차단, (2) 키 재료 밖 코드(프롬프트 조립·envelope 형식) 변경 시 일괄
무효화할 캐시 스키마 버전 네임스페이스 도입, (3) `LLM_CACHE_TTL_SECONDS` 0 이하 값
검증, (4) 캐시 조회·저장 실패를 삼킬 때 warning 로그.

## Implementation Scope

1. `app/adapters/llm/gateway.py` — `output`이 빈 dict이면 `store`를 건너뛴다.
   빈 응답은 provider 이상 신호이므로 TTL 동안 고착시키지 않는다.
2. `app/adapters/llm/cache.py`:
   - 모듈 상수 `CACHE_SCHEMA_VERSION = "v1"` 추가. 키 형식을
     `llm:cache:{CACHE_SCHEMA_VERSION}:{task_type.value}:{YYYYMMDD}:{digest}`로
     변경한다. 키 재료에 반영되지 않는 코드(게이트웨이의 메시지 조립, provider의
     schema instruction, envelope 형식)가 바뀔 때 이 상수를 올려 일괄 무효화한다 —
     이 WHY를 상수 옆 주석 한 줄로 남긴다.
   - digest 재료를 구분자 없는 연결 대신 `json.dumps([...], sort_keys 불필요)` 등
     경계가 보존되는 직렬화로 결합한다(재료 경계 이동으로 인한 이론적 키 충돌 제거).
   - `lookup`·`store`의 예외 삼킴 지점에 `logging.getLogger(__name__)` warning
     한 줄을 추가한다(키·예외 유형 포함, 캐시 값은 로그에 남기지 않는다).
3. `app/core/config.py` — `LLM_CACHE_TTL_SECONDS`에 양수 검증을 추가한다
   (`0` 이하이면 설정 오류로 기동 시 실패). 기존 `""` → `None` 파싱은 유지.
4. 테스트:
   - 빈 output(`{}`)은 store되지 않음(게이트웨이 테스트).
   - `CACHE_SCHEMA_VERSION` 변경 시 키가 달라짐, digest 재료 경계 보존
     (예: payload 끝/prompt 시작 경계 이동 조합이 서로 다른 키).
   - UTC 날짜가 바뀌면 키가 달라짐(기존 공백 보강).
   - `LLM_CACHE_TTL_SECONDS=0`·음수가 설정 검증에서 거부됨.
   - 기존 테스트 전부 통과(키 형식 변경으로 깨지는 단언은 새 형식으로 갱신).

## Out of Scope

- 캐시 동작 구조 변경(정책·budget 순서·CLOUD 전용은 그대로).
- stampede 락, hit/miss 메트릭 수집, Redis 소켓 타임아웃.
- 도메인 서비스·router·privacy·budget·prompts·alembic 변경.

## Protected Files

- `app/adapters/llm/router.py`, `app/adapters/llm/privacy.py`,
  `app/adapters/llm/budget.py`, `app/adapters/llm/prompts/`,
  `app/domains/`, `app/scheduler/`, `alembic/versions/` — 변경 금지.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Rules

- Stay within scope.
- Do not weaken verification.
- Report assumptions and verification results.
- 현재 브랜치(`experiment/138-llm-cache-fable`)를 유지한다. 커밋하지 않는다.
