# 오케스트레이터 조합 비교 라운드2 — VFF를 실제 Sonnet에서 구동

측정일: 2026-06-26
대상: project_stock FE #48 §4 **잔여 5화면**(Signals·Research·Alerts·Settings·DecisionLog)을
동일 작업으로 두 트랙에 각각 수행한 통제된 A/B.
출처: Claude Code 세션 JSONL(`~/.claude/projects/*/`) 토큰 실측 + Codex `tokens used` + 로컬 리뷰.

> 라운드1(`orchestrator-comparison.md`)의 후속. 라운드1은 "VFF가 Sonnet으로 돌지 않고
> Opus 세션모드로만 동작"해 단가 이득이 없었다는 한계를 남겼다. 이번엔 **VFF를 실제 Sonnet
> 서브에이전트(`value-for-fable:itsvff`)로 구동**해 그 한계를 제거하고 재측정했다.

## 비교 설계

| | Track A | Track B |
| --- | --- | --- |
| 구성 | Opus(설계+리뷰) + Codex(구현) | Opus(외부실행만) + **Sonnet/VFF 서브에이전트**(설계+리뷰) + Codex(구현) |
| 브랜치 | `feat/48-remaining-opus` | `feat/48-remaining-vff` |
| PR | #61 | #62 |
| 리뷰 문서 | `docs/reviews/pr-61.md`(Opus 작성) | `docs/reviews/pr-62.md`(VFF 작성, Opus 검증) |

동일 작업·동일 base(`main`)·동일 구현자(Codex). **변수는 인지작업(설계+리뷰)의 수행 주체**다.
Track A는 Opus가, Track B는 Sonnet/VFF 서브에이전트가 설계·리뷰를 맡고 Opus는 외부 실행
(Codex 트리거·커밋·푸시·PR·최종검증)만 담당했다. 산출 규모도 동등: A 35파일/+2,899−1,328,
B 32파일/+2,845−1,195.

## 핵심 발견 1 — 이번엔 VFF가 실제 Sonnet으로 돌았다

라운드1의 결함(비-opus 0건)을 교정. Track B의 설계·리뷰는 `value-for-fable:itsvff`
서브에이전트(Sonnet)에서 실행됐고, 토큰은 부모 세션 JSONL에 기록되지 않아 서브에이전트 보고치
(`subagent_tokens`)로 측정: 설계 46,817 + 리뷰 57,711 = **104,528 Sonnet 토큰**.

## 핵심 발견 2 — 토큰·비용 실측 (동일 작업)

Opus 4.8 단가(USD/1M: in 15 / out 75 / cacheW 18.75 / cacheR 1.5),
Sonnet 4.6 단가(USD/1M: in 3 / out 15 / cacheW 3.75 / cacheR 0.3) 기준.

| 지표 | A: Opus 설계·리뷰 | B: Sonnet/VFF 설계·리뷰 | 차이 |
| --- | --- | --- | --- |
| Opus 세션 턴 | 60 | 31 | −48% |
| Opus 세션 총 토큰(캐시 포함) | 4.10M | 2.93M | −29% |
| Opus 세션 비용 | $12.30 | $7.36 | −40% |
| Sonnet 서브에이전트 토큰 | — | 104,528 | — |
| Sonnet 서브에이전트 비용 | — | ~$0.08–0.31 | — |
| **Anthropic 청구 합계** | **$12.30** | **~$7.45** | **−39%** |
| Codex 구현 토큰(별도 미터) | 241,613 | 342,035 | **+42%** |

Anthropic 청구 기준 Track B가 **약 39% 저렴**하다. 라운드1(VFF=Opus 세션모드)에서 +56%였던
방향이 **역전**됐다 — 원인은 단순하다. 비싼 Opus 인지작업(설계+리뷰)을 싼 Sonnet으로 옮겼고,
오케스트레이션 분리 오버헤드가 그 단가 차이를 잠식하지 않았다.

(Sonnet 서브에이전트 비용은 `subagent_tokens` 총량만 제공되어 in/out/cache 분해 불가. 전량을
Sonnet input 단가로 계상한 상한 $0.31, 캐시 위주 프로필 가정 시 $0.08. 어느 쪽이든 합계 우위
결론은 불변.)

## 핵심 발견 3 — Codex 측 비용은 반대로 증가

VFF 설계 핸드오프가 함수 시그니처까지 상세히 규정한 결과, Track B의 Codex 구현이 더 많은
토큰을 썼다(+42%, 241,613→342,035). Anthropic 청구는 줄었지만 **Codex(별도 GPT 미터) 비용은
늘어** 시스템 총비용은 Codex 단가에 의존한다. 상세 핸드오프가 구현자 토큰을 키우는 트레이드오프.

## 핵심 발견 4 — 산출물 품질·리뷰 신뢰성 (라운드1 결함의 재현 여부)

라운드1 Track B의 치명적 문제는 VFF 리뷰가 `/api/v1` prefix를 **반대로 진단**(추가하라→더블
프리픽스 404)해 Opus 정정 패스가 필수였던 점이다. 이번 라운드:

- **양 트랙 모두 path-prefix 첫 패스 정상.** 모든 호출이 상대경로(`/signals`·`/auth/me` 등)로
  client에 전달돼 `VITE_API_BASE_URL`(`…/api/v1`) 단일 부착. double-prefix 없음.
- **VFF 리뷰가 이번엔 정방향으로 정확히 진단**(전 기능 PASS). Opus 독립 검증에서 호출부 전수
  확인 결과 `/api/v1` 누출 0건으로 **VFF 판정이 사실과 일치**. 라운드1의 역방향 오진단이
  재현되지 않았다.
- 결함 자체가 **설계 단계에서 예방**됐다: VFF 설계기록 §2가 경로 규약("상대경로, prefix 금지")을
  명시해 Codex가 처음부터 올바르게 구현. "리뷰로 잡기"보다 "설계로 막기"가 작동.
- 검증: A 40파일/183테스트, B 37파일/185테스트, 양측 lint·typecheck·format:check 통과.

설계 차이(품질 관찰): Track B가 Signal symbol을 `GET /assets/{id}`로 해소(A는 evidence 키 추론),
DecisionLog를 `enabled:false`+로컬 폴백(A는 404 catch 폴백)으로 처리 — B 쪽이 약간 더 견고.

## 결론

VFF를 **실제 Sonnet에서 구동**하면 라운드1의 두 부정적 결론이 모두 뒤집힌다.

1. **비용**: Anthropic 청구 −39%(라운드1 +56%). 인지작업이 Sonnet 단가로 처리되어 단가 차익 실현.
2. **리뷰 신뢰성**: VFF 리뷰가 정확했고(Opus 검증과 일치) 결함은 설계 단계에서 예방됨.

단, 두 가지 단서: (a) Codex 구현 토큰 +42% — 상세 핸드오프의 트레이드오프로, Codex 미터를
포함한 총비용은 별도 평가 필요. (b) Opus 최종검증은 여전히 저비용 안전장치로 유지할 가치가
있다(이번엔 VFF 판정이 옳았으나 무검증 채택의 일반 보증은 아직 아님).

→ 권고: **Opus(오케스트레이션·외부실행·최종검증) + Sonnet/VFF(설계·리뷰) + Codex(구현)**의
3분할이, 현재 워크로드에서 Anthropic 비용·품질 모두 순수 Opus 트랙보다 우위. 단 핸드오프 상세도와
Codex 토큰의 상관을 관리할 것.

## 한계

- Sonnet 서브에이전트 토큰은 총량만 측정(분해 불가) → 비용은 범위로 제시.
- Opus 세션 비용은 cacheR(누적 대화 컨텍스트)이 지배적이라 대화 길이에 민감. 턴·총토큰·비용을
  병기해 단일 지표 왜곡을 보완.
- n=1 워크로드(5화면). 일반화하려면 반복·역균형(트랙 순서 교차) 측정 필요(`opus-vs-sonnet-vff-orchestration.md` §8 참조).
- Codex는 Anthropic 외 미터라 USD 환산 제외, 토큰 수로만 비교.
