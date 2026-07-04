# 077 · 워커 프로세스 모델 등록 — 중앙 모델 레지스트리

Status: Draft
작성: Claude Code (orchestrator)
관련: 버그 이슈 BE #202, Epic BE #141, PR #199(잡 배선)·#201(cloud 경로 마감).
발견 경로: PR #201 머지 후 `LLM_PROVIDER=mock` 스모크 테스트.

## 1. 배경

RQ 워커에서 `run_llm_analysis_job`이 `LLMAnalysisRun` flush 시점에
`NoReferencedTableError`로 실패한다. 도메인 모델은 FK 대상을 문자열
(`ForeignKey("users.id")`)로만 참조하고 대상 모델을 임포트하지 않으므로, 등록 여부는
프로세스의 임포트 그래프에 달려 있다. FastAPI 앱은 라우터를 통해 전 모델이 로드되지만
워커 프로세스는 잡 모듈이 끌어오는 모듈만 로드한다. `run_llm_analysis_job`의 그래프에
`users` 모델이 없어 `llm_analysis_runs.user_id` FK 해석이 실패한다.

llm-analysis 잡만의 문제가 아니다. 임포트 그래프 밖의 FK 대상이 생기는 조합마다 같은
방식으로 터지는 잠재 결함이며, pytest는 conftest가 전 모델을 임포트해 재현하지 못한다.

## 2. 범위

포함:

- `app/db/models.py`(신규): 전 도메인 모델 임포트 레지스트리.
- `alembic/env.py`(수정): 개별 모델 임포트 18줄을 레지스트리 임포트로 대체.
- `app/worker/jobs/__init__.py`(수정): 레지스트리 임포트로 워커 잡 로딩 시 전 모델 등록.
- 워커 임포트 컨텍스트 회귀 테스트.

비포함:

- 모델·FK 정의 변경, alembic revision.
- 워커 잡 로직 변경.

## 3. 구성 요소

### 3.1 모델 레지스트리 (`app/db/models.py`, 신규)

| 항목 | 책임 |
|---|---|
| `import app.domains.<domain>.model` × 18 (`theses.conflict_model` 포함) | 전 도메인 모델을 `Base.metadata`에 등록하는 단일 지점 |

alembic `env.py`의 기존 임포트 목록을 그대로 옮긴다. 이후 새 모델 추가 시 이 파일만
갱신하면 앱·워커·alembic이 함께 반영된다.

### 3.2 임포트 지점

| 파일 | 변경 |
|---|---|
| `alembic/env.py` | 개별 임포트 블록 → `import app.db.models  # noqa: F401` |
| `app/worker/jobs/__init__.py` | `import app.db.models  # noqa: F401` — RQ가 잡 모듈을 임포트하면 패키지 `__init__`이 먼저 실행되므로 모든 잡에 일괄 적용 |

## 4. Decisions

- **Decision YY — 중앙 모델 레지스트리 모듈을 도입한다.** 각 모델이 FK 대상 모델을
  개별 임포트하는 방식은 새 FK가 생길 때마다 누락이 재발할 수 있고 도메인 간 임포트를
  퍼뜨린다. alembic `env.py`에 이미 같은 목록이 존재하므로 이를 단일 모듈로 승격해
  재사용한다.
- **Decision ZZ — 워커 쪽 임포트 지점은 `app/worker/jobs/__init__.py`로 한다.** 잡
  모듈마다 임포트를 반복하면 새 잡 추가 시 누락될 수 있다. `app/db/session.py`에서
  임포트하는 방식은 세션 모듈에 도메인 의존을 역류시키므로 기각한다.

## 5. 마이그레이션

없음. metadata 등록 시점의 문제이며 스키마 변경이 아니다.

## 6. 테스트

- 서브프로세스에서 잡 모듈만 임포트한 뒤(`import app.worker.jobs.llm_analysis`)
  `Base.metadata` 안의 모든 FK가 참조하는 테이블이 metadata에 존재하는지 검증한다.
  conftest가 전 모델을 미리 임포트하는 동일 프로세스 pytest로는 재현되지 않으므로
  서브프로세스가 필수다.
- 기존 테스트 전부 통과.

## 7. ADR 판단

불필요. 아키텍처 선택이 아니라 기존 구조(문자열 FK + 프로세스별 임포트 그래프)의 결함
마감이다.

## 8. Failure Record 판단

필요. "RQ 워커 프로세스에서 FK 대상 모델 미등록" 패턴은 재발 가능하고 pytest로 잡히지
않는 유형이므로 `docs/failures/`에 기록한다(핸드오프 범위에 포함).
