# Codex Handoff Task

## Source Issue

BE #349 — 판단 기록 데이터 모델·마이그레이션 (6테이블 분리). Epic #347. ADR-016.

## Task Summary

판단 기록(Decision Log) 재설계의 데이터 계층만 구현한다. `app/domains/decision_logs`의
ORM 모델과 enum을 6테이블 구조로 재편하고, Alembic 마이그레이션을 추가한다. API·service·
schema의 신규 유스케이스는 이 태스크 범위가 아니다(후속 #350~#352).

## Goal

이 태스크가 끝나면 다음이 참이어야 한다.

- `app/domains/decision_logs/types.py`에 재설계 enum이 모두 정의돼 있다.
- `app/domains/decision_logs/model.py`에 6개 ORM 모델이 정의돼 있다:
  `DecisionLog`(재편), `DecisionEvidence`, `DecisionRisk`, `DecisionReviewTrigger`,
  `DecisionSnapshot`, `DecisionReview`.
- 새 Alembic 리비전이 6개 테이블을 생성하고, 기존 `decision_logs` 테이블은 신 스키마로
  교체된다(down_revision = 현재 head `c3d4e5f60069`).
- `uv run ruff check .`, `uv run mypy .`, `uv run pytest`가 모두 통과한다.

## Background

정본 계약은 `docs/designs/348-decision-log-redesign.md`(§2 enum, §3 테이블)와 ADR-016이다.
반드시 이 두 문서를 먼저 읽고 그대로 따른다. 요지:

- 기존 단일 테이블 `decision_logs`(ticker·reason·decision_status·cognitive_risks JSON 등)를
  재설계 모델이 supersede한다. 기존 도메인 파일은 현재 단일 테이블 기준으로 작성돼 있다
  (`model.py`/`types.py`/`schema.py`/`repository.py`/`service.py`/endpoint). 이 태스크는
  `model.py`와 `types.py`만 재편 대상이다.
- PK는 프로젝트 관례대로 `Integer` autoincrement(설계문서 §3, ADR-016 UUID는 개념 표기).
- 타임스탬프는 `app/db/base.py`의 `TimestampMixin`(`created_at`/`updated_at`).
- 모델은 `app/db/base.py`의 `Base`를 상속. `app/db/models.py`가 이미
  `import app.domains.decision_logs.model`로 등록하므로 추가 import 불필요(신규 모델이 같은
  모듈에 있으면 자동 등록됨).
- 마이그레이션은 **수동 작성**한다(autogenerate 금지 — 샌드박스는 DB 연결 불가). 최근
  선례 `alembic/versions/c3d4e5f60069_create_alert_unified_models.py`가 한 리비전에서 여러
  `op.create_table`을 만드는 패턴이니 참고한다. 리비전 ID는 그 계열을 이어
  `c3d4e5f6006a` 형식으로 둔다.

## Implementation Scope

Codex가 변경할 수 있는 파일:

- `app/domains/decision_logs/types.py` — enum 재정의(설계문서 §2 전체).
- `app/domains/decision_logs/model.py` — 6개 모델(설계문서 §3.1~§3.6 컬럼·타입·제약 그대로).
- `alembic/versions/c3d4e5f6006a_redesign_decision_logs.py` — 신규 리비전(6테이블 생성 +
  기존 decision_logs 교체). up/down 모두 구현.
- `tests/test_decision_logs_models.py` — 신규(모델 라운드트립·enum 값·관계 최소 검증).

## Out of Scope

- `schema.py`, `repository.py`, `service.py`, `app/api/v1/endpoints/decision_logs.py`의
  **신규 유스케이스 구현**(overview/activate/review-queue/필터 등)은 후속 태스크(#350~#352).
- 다만 위 파일들이 재편된 모델·enum과 import 불일치로 **깨지면**, 컴파일·기존 테스트가
  통과하도록 **최소한의 수선**만 허용한다(아래 Requirements 참조).
- FE, 다른 도메인, Alert 연동, 복기/버전 API 로직.

## Protected Files

없음. `alembic/`은 신규 리비전 추가만 하고 기존 리비전 파일은 수정하지 않는다.

## Requirements

- 설계문서 §2·§3의 enum 값·컬럼명·타입·제약·기본값을 **정확히** 따른다. 임의 추가·개명
  금지.
- `DecisionReview`(§3.6)는 테이블만 생성하고 API는 열지 않는다.
- 관계(FK `decision_id → decision_logs.id`)는 `ForeignKey`로 건다. relationship() 매핑은
  최소로(필요 시 조회 편의용, 없어도 됨).
- 기존 `schema.py`/`repository.py`/`service.py`/endpoint가 사라진 컬럼·enum을 참조해
  import·타입 오류가 나면, **기존 CRUD 계약을 유지하도록 최소 수선**한다. 새 필드명으로
  매핑이 애매하면, 해당 엔드포인트/메서드가 재설계 필드 위에서 동작하도록 보수적으로
  조정하되 신규 기능은 넣지 않는다. 목표는 mypy·pytest 그린이지 기능 확장이 아니다.
- 기존 테스트 `tests/test_decision_logs.py`가 계약 변경으로 더 이상 유효하지 않은 필드를
  검증한다면, 재설계 계약(설계문서 §3.1 컬럼)에 맞게 **갱신**한다. 삭제가 아니라 갱신이다.
- wire 컨벤션: 시각은 `DateTime(timezone=True)`, 금액류 없음(이번 모델엔 Decimal 컬럼 없음).

## Test Requirements

- `tests/test_decision_logs_models.py`(신규): `DecisionLog` + 각 부속 테이블 1건씩 생성·
  조회 라운드트립, enum 값이 문자열로 저장되는지, FK 연결이 성립하는지 확인.
- `tests/test_decision_logs.py`(갱신): 재편된 필드에 맞춰 기존 CRUD 테스트가 통과하도록
  수정. 신규 유스케이스 테스트는 추가하지 않는다.
- 마이그레이션 up/down이 sqlite 테스트 픽스처에서 깨지지 않아야 한다(테스트가 메타데이터
  기반 create_all을 쓰면 리비전 실행과 별개지만, 모델 정의가 정합해야 한다).

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

세 개 모두 통과해야 한다(BE CI 3종과 동일).

## Documentation Impact

설계문서(`docs/designs/348-decision-log-redesign.md`)와 ADR-016은 이미 작성돼 있다. 구현이
설계와 어긋나면 코드가 아니라 설계를 따르되, 불가피하게 벗어나면 설계문서에 한 줄 주석으로
사유를 남긴다(가급적 벗어나지 않는다).

## ADR Need

불필요. ADR-016이 이미 결정을 담았다. 이 태스크는 그 구현이다.

## Failure Record Need

불필요(정상 구현 태스크). 구현 중 되풀이될 함정을 발견하면 커밋 메시지에 남긴다.

## Risk Level

Medium — DB 스키마 재편이며 기존 CRUD 파일과의 정합을 맞춰야 한다. 단, 기존 데이터가
mock·테스트 수준이라 데이터 손실 위험은 낮다. human-gate는 사람 승인 완료.

## Expected Output

- 변경 파일: `types.py`, `model.py`, 신규 alembic 리비전, 신규/갱신 테스트, (필요 시)
  `schema.py`/`repository.py`/`service.py`/endpoint 최소 수선.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/348-decision-log-redesign`에 그대로 커밋(새 브랜치 만들지 말 것).
  커밋 메시지는 한국어 `feat: ...` 형식, 이슈 `#349` 참조.
