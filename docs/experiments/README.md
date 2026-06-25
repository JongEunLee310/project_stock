# Experiments

오케스트레이션 방식·도구 조합 등 워크플로 선택을 실측으로 비교한 케이스 스터디를 모은다.
지식 베이스(`docs/knowledge/`)의 안정적 규약과 달리, 여기엔 측정 조건·한계가 붙은 실험 기록을 둔다.

## 문서

- `opus-vs-sonnet-vff-orchestration.md` — 단일 세션 관찰(n=1)과 통제 설계 방법론(§8).
- `orchestrator-comparison.md` — 라운드1: Opus+Codex vs Opus+VFF(Opus 세션모드)+Codex. VFF가
  Sonnet으로 돌지 않아 단가 이득 미실현, Track A 우위.
- `orchestrator-comparison-round2-vff-sonnet.md` — 라운드2: VFF를 실제 Sonnet 서브에이전트로
  구동. Anthropic 청구 −39%로 결론 역전, 단 Codex 토큰 +42% 트레이드오프.

## 작성 규칙

측정일·대상·출처·단가 기준을 명시하고, 한계 절을 반드시 둔다. 결론은 측정 조건에 종속됨을 밝힌다.
파일명은 lowercase kebab-case.
