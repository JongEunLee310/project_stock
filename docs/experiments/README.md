# Experiments

오케스트레이션 방식·도구 조합 등 워크플로 선택을 실측으로 비교한 케이스 스터디를 모은다.
지식 베이스(`docs/knowledge/`)의 안정적 규약과 달리, 여기엔 측정 조건·한계가 붙은 실험 기록을 둔다.

## 문서

- `opus-vs-sonnet-vff-orchestration.md` — 단일 세션 관찰(n=1)과 통제 설계 방법론(§8).
- `orchestrator-comparison.md` — 라운드1: Opus+Codex vs Opus+VFF(Opus 세션모드)+Codex. VFF가
  Sonnet으로 돌지 않아 단가 이득 미실현, Track A 우위.
- `orchestrator-comparison-round2-vff-sonnet.md` — 라운드2: VFF를 실제 Sonnet 서브에이전트로
  구동. Anthropic 청구 −39%로 결론 역전, 단 Codex 토큰 +42% 트레이드오프.
- `fable-codex-high-vs-opus-vff-codex-medium.md` — 라운드3: 동일 이슈(BE #138) 양 브랜치
  병렬 구현·블라인드 채점. Fable 5+Codex(high)가 70 vs 60으로 우세, 단 n=1·축 미분리.
- `orchestrator-comparison-round4-plan.md` — 라운드4 계획: BE #139, codex effort medium
  고정으로 오케스트레이터 축 단독 분리, 팔별 토큰 격리, 이중 판정(Fable 5 + codex xhigh).
- `orchestrator-comparison-round4.md` — 라운드4 결과: 이중 블라인드 판정 일치로
  Opus+VFF+Codex(medium) 우세(J1 86:80, J2 65:62). 라운드3 effort 통제 실패 정정 포함.
  결합 결론: 조합 전환 근거 없음, 기존 표준 유지.

## RAG Evaluation

- `rag-eval-set.json` — #444 검색 품질 평가 세트. `relevant_title_pattern`은 해당
  종목에 연결된 원문 제목의 PostgreSQL `~*` 정규식이며, `null`은 부정 질문이다.
- `scripts/evaluate_rag_retrieval.py` — 질문별 검색 지표, 긍정·부정 집계, 후보 원점수
  분포와 유사도 하한 sweep을 Markdown 표로 출력한다. 평가 시각은 세트의
  `reference_now`로 고정하며, 검색 기간은 `lookback_days`를 사용한다.

```bash
uv run python scripts/evaluate_rag_retrieval.py --eval-set docs/experiments/rag-eval-set.json
uv run python scripts/evaluate_rag_retrieval.py --eval-set docs/experiments/rag-eval-set.json --json-out /tmp/rag-evaluation.json --thresholds 0.30,0.40,0.50
uv run python scripts/evaluate_rag_retrieval.py --eval-set docs/experiments/rag-eval-set.json --with-llm
```

실측에는 평가 세트와 대응하는 PostgreSQL 데이터 및 현재 모델의 뉴스 임베딩이 필요하다.
기존 환경 설정의 임베딩·벡터 저장소 provider를 사용하며, `--with-llm`은 LLM provider도
사용하므로 해당 provider의 외부 호출·비용이 발생할 수 있다. 기본 실행은 LLM을 호출하지 않는다.
질문별 임베딩과 후보 검색은 각각 1회이며, sweep과 LLM 서비스는 같은 후보를 재사용한다.
종목 기호가 여러 시장에 중복되거나 없는 경우 평가를 중단한다.

관련 근거 수는 종목에 연결된 패턴 일치 원문의 고유 ID 수이며 검색 기간으로 다시 제한하지 않는다.
precision은 후처리된 청크 기준이고, 같은 원문의 여러 청크도 각각 센다. 근거가 없으면
precision은 `null`이고, 집계 평균에서 `null`은 제외한다. 긍정 질문은 패턴 유무로 분류하므로
관련 원문이 0건이어도 긍정 hit·top1 분모에 포함한다. 후보 분포는 후처리 전 점수를 사용한다.
LLM 오류는 질문별 `error`에 기록하고 계속한다. 서비스가 오류를 근거 부족 응답으로 처리하면
그 응답도 insufficient 비율에 포함하고, 응답 자체가 없는 오류는 비율에서 제외한다.
측정 실행과 결과 기록은 오케스트레이터가 담당한다.

## 작성 규칙

측정일·대상·출처·단가 기준을 명시하고, 한계 절을 반드시 둔다. 결론은 측정 조건에 종속됨을 밝힌다.
파일명은 lowercase kebab-case.
