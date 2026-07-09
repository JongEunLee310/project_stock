# Codex Handoff Task

## Source Issue

#245 — 로컬 compose에 RQ worker·scheduler 서비스 추가 (분석 잡 소비 공백 해소)

설계 문서 없음 — 신규 도메인·의존성·아키텍처 결정이 없는 compose 구성 변경이라 design-record-policy상 불요. 이슈 #245와 본 핸드오프가 정본이다.

## Task Summary

`docker-compose.yml`에 `worker`(rq worker)·`scheduler`(rq cron) 서비스를 추가해, 트리거(#243, FE #129)로 큐잉된 분석 잡이 로컬 스택에서 실제로 소비되게 한다.

## Goal

- `docker compose up` 시 worker가 default 큐를 소비하고, scheduler가 cron 등록을 수행한다.
- `docker compose config`가 오류 없이 통과한다.
- 코드(python) 변경 없음 — `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 결과가 기존과 동일하다.

## Background

- 현재 `docker-compose.yml`은 `backend`·`postgres`·`redis`만 정의한다. 잡 큐잉 경로는 완성됐지만 소비 프로세스가 없다.
- 스케줄러 실행 명령의 정본: `uv run rq cron app/scheduler/cron_config.py -u $REDIS_URL` (출처: `docs/knowledge/product-workflow.md` 스케줄러 섹션).
- worker 실행은 RQ 표준 `rq worker` (default 큐, `-u $REDIS_URL`). backend 이미지의 실행 관례는 uv 기반이므로 `uv run rq worker ...` 형태로 backend `command`(uvicorn) 패턴을 따른다.
- `ANALYSIS_SCHEDULE_ENABLED`는 `app/scheduler/registry.py` 임포트 시점에 평가되므로 scheduler 서비스에 env가 전달되어야 하며, 기본(false)에서는 분석 스케줄이 비활성으로 유지된다.

## Implementation Scope

1. **`docker-compose.yml`**
   - `worker` 서비스: `build: .`, backend와 동일한 `environment`(DATABASE_URL·REDIS_URL)·`env_file`(.env, required: false)·`volumes`(`.:/app`, `/app/.venv`)·`depends_on`(postgres·redis healthy). `command`는 uv 기반 rq worker (default 큐, REDIS_URL 사용). `ports` 불필요.
   - `scheduler` 서비스: worker와 동일 구성에 `command`만 rq cron (`app/scheduler/cron_config.py`).
2. **문서** — `README.md`와 `docs/knowledge/product-workflow.md`에서 로컬 실행·스케줄러 실행을 서술하는 부분이 있으면 compose로 worker·scheduler가 함께 뜬다는 내용으로 갱신한다. 서술이 없으면 추가하지 않는다 (확인 후 판단, 변경 시 해당 파일만).

## Out of Scope

- 배포용 compose·CD 파이프라인·Dockerfile 변경
- worker 수평 확장, 큐 분리, healthcheck 신설
- python 코드·스케줄 로직 변경
- `.env.example` 변경 (ANALYSIS_SCHEDULE_ENABLED 항목은 이미 있음)

## Protected Files

변경할 보호 파일 없음. `.github/workflows/`는 건드리지 않는다.

## Requirements

1. `worker`·`scheduler` 서비스가 backend와 동일한 빌드·env·볼륨·의존 구성을 가진다.
2. scheduler의 command가 product-workflow.md의 정본 명령과 일치한다 (compose 내부에서는 `REDIS_URL` env 사용).
3. `docker compose config` 통과.
4. python 코드 무변경.

## Test Requirements

compose 구성은 pytest 대상이 아니다. 검증은 `docker compose config`와 기존 테스트 스위트 무회귀로 갈음한다.

## Verification Commands

```
docker compose config
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

Implementation Scope 2 참고. 그 외 없음.

## ADR Need

불필요. 기존 스케줄러 결정(ADR-003)의 실행 형상 반영이다.

## Failure Record Need

불필요.

## Risk Level

낮음(Low). 서비스 추가만 있고 기존 서비스 정의는 변경하지 않는다. `--reload` 없는 워커 특성상 코드 변경 시 워커 재시작이 필요하다는 점을 문서 갱신 시 함께 언급하면 좋다.

## Expected Output

- `docker-compose.yml`에 두 서비스 추가
- (해당 시) README/product-workflow 로컬 실행 서술 갱신
- 검증 4종 결과 보고

## Rules

- 현재 브랜치(`feat/245-compose-worker`) 유지 — 새 브랜치 생성 금지. 커밋 금지 (오케스트레이터가 수행).
- 기존 `backend`·`postgres`·`redis` 서비스 정의는 변경하지 않는다.
- 범위 밖 파일 변경 금지.
