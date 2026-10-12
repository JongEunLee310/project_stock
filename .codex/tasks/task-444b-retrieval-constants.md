# Codex Handoff Task

## Source Issue

#444 보정 — 평가 결과에 따른 검색 상수 조정 (에픽 #438)

## Task Summary

orchestrator가 평가 세트로 측정한 결과에 따라 `app/domains/rag/retrieval.py`의 상수 두 개를 바꾸고,
깨지는 테스트를 맞추고, 설계 문서에 근거를 남긴다.

## Background

측정(2026-10-12, 평가 세트 18문항, 실제 Ollama `bge-m3`, pgvector, 로컬 DB 복제본 2,703건) 결과는
다음과 같다.

| 설정 | 긍정 hit@8 | 긍정 precision@8 | 긍정 top1 | 부정 근거 0건 비율 |
|---|---|---|---|---|
| 하한 0.30, TITLE_ONLY 가중치 0.8(현재) | 0.786 | 0.554 | 0.714 | 0.000 |
| 하한 0.30, 가중치 1.0 | 0.857 | 0.571 | 0.786 | 0.000 |
| 하한 0.50, 가중치 1.0 | 0.857 | 0.593 | 0.786 | 0.000 |
| 하한 0.55, 가중치 1.0 | 0.786 | 0.667 | — | 0.500 |

- 코퍼스의 98%가 `TITLE_ONLY`(2,652/2,703건)라서, 가중치 0.8은 결과적으로 `SUMMARY` 44건만 끌어올려
  관련 헤드라인을 밀어냈다.
- 관련·비관련 후보의 원점수 분포가 겹친다(중앙값 0.573 대 0.526). 하한만으로 부정 질문을 거를 수는
  없다. 부정 질문은 LLM의 `insufficient_evidence` 판정이 4/4 걸러 냈다.

## Implementation Scope

1. `MIN_SCORE = 0.5`, `TITLE_ONLY_WEIGHT = 1.0`으로 바꾼다. 가중치 로직은 지우지 않는다. 2차에서
   본문이 있는 공시 근거(`FULL`)가 들어오면 다시 조정할 수 있게 상수로 남긴다.
2. `postprocess_hits`의 `min_score` 기본값이 정의 시점에 고정되는 문제를 고친다. 기본값을
   `None`으로 두고 함수 안에서 `MIN_SCORE`를 읽게 한다. 평가 스크립트의 같은 패턴
   (`scripts/evaluate_rag_retrieval.py`의 `min_score: float = MIN_SCORE` 기본값, 출력 머리의
   `"min_score": MIN_SCORE`)도 같은 방식으로 바꾼다. 실험에서 모듈 상수를 바꿔도 서비스 호출에
   반영되지 않았던 문제다.
3. 상수 변경으로 깨지는 테스트를 고친다. 테스트가 특정 상수 값에 기대지 않도록 가능하면 상수를
   import해 계산한다. 가중치 로직 자체를 검증하는 테스트는 가중치를 명시적으로 바꿔(monkeypatch) 유지한다.
4. 설계 438 §5.2의 검색 후처리 규칙에 새 값과 위 표, 근거(가중치 역효과, 분포 겹침, 부정 질문은 LLM
   판정에 맡김)를 반영한다. 값 옆의 "가정" 표기는 "평가 근거(2026-10-12)"로 바꾼다.

## Out of Scope

- 평가 세트, 측정 실행, 결과 문서(orchestrator)
- 질문 재작성, 하이브리드 검색

## Protected Files

없음.

## Test Requirements

- 하한 0.5 경계(0.499 제외, 0.5 포함)
- 가중치 1.0에서 `TITLE_ONLY` 점수가 바뀌지 않음
- monkeypatch로 `MIN_SCORE`를 바꾸면 `postprocess_hits()` 기본 호출에 반영됨
- 기존 검증 강도를 낮추지 않는다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low — 상수와 기본 인자 처리 변경.

## Expected Output

- 현재 브랜치 `feat/444-rag-eval-set`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋으로 두고 보고한다. push와 PR 생성은 하지 않는다.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
