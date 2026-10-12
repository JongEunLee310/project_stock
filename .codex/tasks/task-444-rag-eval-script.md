# Codex Handoff Task

## Source Issue

#444 — [BE] RAG 1차: 검색 품질 평가 세트·기준선 (에픽 #438)

## Task Summary

orchestrator가 만든 평가 세트(`docs/experiments/rag-eval-set.json`)로 검색 품질을 측정하는 스크립트를
만든다. 기본 실행은 검색만 측정하고, 옵션으로 실제 LLM 응답까지 측정한다. 유사도 하한을 바꿔 가며
결과를 비교하는 sweep도 출력한다. 측정 실행과 결과 기록은 orchestrator가 한다.

## Goal

- `uv run python scripts/evaluate_rag_retrieval.py --eval-set docs/experiments/rag-eval-set.json`이
  질문별 지표, 집계 지표, 하한 sweep 표를 Markdown으로 출력한다.
- `--json-out <path>`를 주면 같은 내용을 JSON으로도 저장한다.
- `--with-llm`을 주면 `ResearchQAService.ask`까지 호출해 LLM 지표를 추가한다.
- 순수 계산 함수에 단위 테스트가 있다(DB·임베딩 없이).

## Background

- 평가 세트 형식: `docs/experiments/rag-eval-set.json`(이미 있음, 수정하지 않는다)
  - 최상위: `reference_now`(ISO 8601), `lookback_days`, `questions[]`
  - 질문: `id`, `symbol`, `question`, `relevant_title_pattern`(PostgreSQL `~*` 정규식, 또는 `null`이면
    부정 질문)
- 관련 근거 정의: 해당 종목(`symbol`로 찾은 asset)에 `news_items`로 연결된 `raw_news_events` 가운데
  제목이 패턴에 맞는 원문 id 집합. 평가 스크립트는 rag 도메인 코드가 아니므로 이 집합을 SQL로 직접
  조회해도 된다(ADR-018 R2는 `app/domains/rag/` 코드에 적용된다).
- 검색 경로는 서비스와 같아야 한다. `get_embedder()`, `get_vector_store(db)`, `ChunkFilter`(현재 모델,
  해당 asset, `NEWS`, `reference_now - lookback_days` 이후), `CANDIDATE_K`, `postprocess_hits`
  (`app/domains/rag/retrieval.py`)를 그대로 쓴다.
- `now`는 `reference_now`로 고정한다. 데이터가 2026-07-23까지라 실제 현재 시각을 쓰면 기간 필터에
  걸린다.
- `ResearchQAService`는 `now`를 주입받는다(`app/domains/rag/service.py`).
- 기존 스크립트 관례: `scripts/backfill_rag_embeddings.py`(argparse, `sys.path` 처리, `SessionLocal`)
- 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. `app/domains/rag/retrieval.py`의 `postprocess_hits`에 `min_score: float = MIN_SCORE` 키워드 인자를
   추가한다. 기존 호출과 동작은 바뀌지 않는다. sweep에서 하한만 바꿔 같은 후처리를 재사용하기 위해서다.
2. `scripts/evaluate_rag_retrieval.py`
   - 인자: `--eval-set`(필수), `--json-out`(선택), `--with-llm`(선택), `--thresholds`(기본
     `0.30,0.35,0.40,0.45,0.50,0.55,0.60`)
   - 질문별로 임베딩 1회, 후보 검색 1회(`CANDIDATE_K`)만 하고, 하한별 결과는 같은 후보에 후처리를 다시
     적용해 계산한다.
   - 질문별 지표(기본 하한 `MIN_SCORE` 기준)
     - `relevant_total`: 관련 근거 수
     - `evidence_count`: 후처리 후 근거 수
     - `hit_at_k`: 근거 중 관련 근거가 하나라도 있는지(긍정 질문)
     - `precision_at_k`: 근거 중 관련 근거 비율(근거 0건이면 `null`)
     - `top1_relevant`
     - `max_score`, 관련 후보의 최고·최저 점수, 비관련 후보의 최고 점수(후처리 전 원점수)
   - 집계 지표
     - 긍정 질문: 평균 `hit_at_k`, 평균 `precision_at_k`, `top1` 비율
     - 부정 질문: 근거 0건 비율, 평균 `evidence_count`, 평균 `max_score`
     - 후보 원점수 분포: 관련 후보와 비관련 후보 각각의 중앙값과 최댓값
   - 하한 sweep 표: 하한마다 긍정 평균 `hit_at_k`, 긍정 평균 `precision_at_k`, 부정 근거 0건 비율
   - `--with-llm`이면 질문마다 `ResearchQAService(..., now=reference_now).ask`를 호출해
     `insufficient_evidence`, 답변 항목 수, 소요 시간(초)을 기록한다. 집계로 긍정 질문의 insufficient
     비율, 부정 질문의 insufficient 비율, 평균 소요 시간을 낸다. LLM 오류는 질문 단위로 기록하고 계속한다.
   - 출력은 Markdown 표다. 숫자는 소수 셋째 자리까지.
   - 계산 로직(지표 계산, 집계, sweep)은 DB와 무관한 순수 함수로 분리해 테스트할 수 있게 한다. 위치는
     `scripts/` 안의 같은 파일이어도 되고, 테스트가 import하기 어렵다면 `app/domains/rag/evaluation.py`로
     둔다.
3. `docs/experiments/README.md`에 RAG 평가 세트와 스크립트 사용법 항목을 기존 형식대로 추가한다.

## Out of Scope

- 평가 세트 파일 수정, 측정 실행, 결과 문서 작성(orchestrator)
- `MIN_SCORE` 등 상수 값 변경(측정 후 orchestrator가 판단)
- CI 편입

## Protected Files

없음.

## Test Requirements

- 순수 함수 단위 테스트: 질문별 지표(관련 있음·없음·근거 0건), 긍정·부정 집계, sweep(같은 후보에서
  하한이 올라갈수록 근거 수가 줄어듦), 후보 점수 분포
- `postprocess_hits(min_score=...)`가 기본값일 때 기존 테스트 결과와 같고, 높은 하한에서 근거가 줄어듦
- 스크립트 인자 파싱(`--thresholds` 파싱, 잘못된 값 오류)

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run python scripts/evaluate_rag_retrieval.py --help
```

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low — 오프라인 평가 스크립트와 후처리 함수의 하위 호환 인자 추가.

## Expected Output

- 현재 브랜치 `feat/444-rag-eval-set`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정, 검증 명령별 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
