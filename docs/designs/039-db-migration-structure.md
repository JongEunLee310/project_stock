# 039 DB Migration Structure

## Scope

DB 스키마 변경을 안정적으로 관리하도록 Alembic 구조를 정리한다. 모든 도메인 모델이 autogenerate 대상에 등록되도록 `env.py` import 누락을 보완하고, single head 상태를 유지하며, 마이그레이션 실행 방법을 문서화한다. 기존 마이그레이션 파일을 재작성하거나 스키마를 바꾸지 않는다(정리·검증·문서화 범위).

## Current State

- Alembic 설정됨: `alembic.ini`(`script_location`), `alembic/env.py`가 `settings.DATABASE_URL` 주입 + `Base.metadata` 사용.
- 현재 head: `c3d4e5f60055`(single head). 과거 merge 마이그레이션(`4d5e6f708192`, `8c3f0d2b7a91`) 존재.
- **공백**: `env.py`가 `alerts`, `signals`, `reports` 모델을 import하지 않는다 — 해당 테이블은 마이그레이션 파일이 존재하나 `--autogenerate` diff 대상에서 누락된다.
- watchlist/portfolio/research/alert 테이블은 마이그레이션에 반영되어 있음(versions 디렉터리 확인).

## Tasks

| 항목 | 내용 |
| --- | --- |
| 모델 등록 보완 | `env.py`에 `alerts`/`signals`/`reports` 모델 import 추가, 전체 도메인 모델 등록 일관성 확보 |
| Head 정합성 | `alembic heads`가 single head인지 확인, `upgrade head`/`downgrade base` 왕복 검증 |
| 실행 문서화 | README/문서에 마이그레이션 생성·적용·롤백 명령 정리 |

## Functions

- `alembic/env.py` — 누락된 도메인 모델 import 추가(autogenerate가 전체 테이블을 인식하도록). import 외 로직 변경 없음.
- 문서(`README.md` Alembic 섹션 또는 `docs/` 내 마이그레이션 가이드) — `uv run alembic upgrade head`, `revision --autogenerate`, `downgrade` 절차 명시.

## Decisions

- 기존 마이그레이션 파일은 squash/재작성하지 않는다 — 추적성 유지, 재현 가능한 현 체인을 보존.
- `env.py` import 누락 보완은 향후 `--autogenerate` 정확도를 위한 것 — 이번에 스키마 변경용 신규 리비전을 만들지 않는다(모델과 기존 마이그레이션이 이미 일치한다는 전제 검증).
- 검증 중 누락 테이블/불일치가 발견되면 해당 사실을 보고하고 보정 리비전 필요 여부를 핸드오프에서 판단.
