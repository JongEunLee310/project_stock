# 실험 기록: Opus vs Sonnet+VFF 오케스트레이션 비교

작성 2026-06-25. API 계약 정렬 6라운드(BE#97 가격 시계열 / FE#47 도메인 재정렬)를 동일 작업쌍으로 두고, 오케스트레이터를 달리해 관찰한 기록. 통제된 벤치마크가 아니라 **단일 세션 관찰**이므로 수치는 추세 참고용이다.

## 1. 목적

"Sonnet + VFF(value-for-fable, Sonnet 세션에 Fable 5 운영구조를 입힌 모드)가 Opus를 대체할 수 있는가"를, 같은 Codex 구현자 위에서 실제 작업으로 확인.

## 2. 실험 구도

| 단계 | BE 트랙 (BE#97) | FE 트랙 (FE#47) |
| --- | --- | --- |
| 설계·계약 동결 | Opus | **Sonnet+VFF** |
| 핸드오프 작성 | Opus | **Sonnet+VFF** |
| 구현 | Codex | Codex |
| 검증 실행 | Opus | Opus |
| diff 리뷰 | Opus | **Sonnet+VFF** |
| 외부 실행(커밋·push·PR·gh) | Opus | Opus |

FE 트랙은 도중에 **3자 분업**으로 정착했다(아래 §6 발견 참조): Opus=오케스트레이터(외부 실행)만, Sonnet+VFF=설계·리뷰, Codex=구현.

## 3. 수치 (세션 텔레메트리)

### 3.1 Sonnet+VFF (itsvff 서브에이전트) 호출별

| 호출 | 토큰 | 툴 사용 | 소요 |
| --- | --- | --- | --- |
| FE↔BE 갭 조사 | 52,052 | 34 | 173.7s |
| FE#47 설계 v1 | 54,048 | 38 | 293.8s |
| FE#47 설계 확정(OQ 반영) | 77,724 | 54 | 659.0s |
| FE#47 구현위임 거부 #1 | 78,022 | 0 | 11.1s |
| FE#47 구현위임 거부 #2 | 79,302 | 0 | 13.5s |
| FE#47 diff 리뷰 | 101,090 | 33 | 163.3s |

> 캐비엇: `subagent_tokens`는 호출(재개)마다 누적 트랜스크립트를 다시 읽으므로 **단순 합산하면 중복 계상**된다. 표는 호출별 청구 토큰이지 순증분이 아니다.

- **생산적 설계·리뷰 작업**(v1+확정+리뷰): 약 232.9k 토큰 / 125 툴 / 1,116s.
- **거부로 낭비된 spend**: 약 157.3k 토큰(툴 0, 산출 없음) — §6의 권한 경계 마찰 비용.

### 3.2 Codex (구현, 별도 예산)

| 트랙 | 사용 토큰 |
| --- | --- |
| BE#97 구현 | 201,219 |
| FE#47 구현 | 128,544 |

### 3.3 Opus (메인 세션 전체, 실측)

세션 트랜스크립트(JSONL)에서 집계한 이 Opus 메인 세션 누적. **양 트랙 + VFF 역할 협의 + codex hang 디버깅 + 본 문서화까지 전부 포함**하며, 단일 세션이라 역할·트랙별 분리는 불가하다.

| 항목 | 값 |
| --- | --- |
| assistant 턴 | 309 |
| input (uncached) | 94,152 |
| cache_creation | 2,000,833 |
| cache_read | 43,617,208 |
| output | 444,284 |
| 합계 (캐시 포함, 청구 기준) | 46,156,477 |
| 추정 비용 | 약 $45.9 |

- **cache_read 43.6M이 압도적** — 긴 단일 세션을 309턴 재처리한 컨텍스트 오버헤드다. "고유 작업량"이 아니라 캐시 포함 청구 토큰. 실제 산출량 프록시는 output 444k.
- 비용 추정 단가(per 1M): input $5 · output $25 · cache write $6.25(1.25x) · cache read $0.50(0.1x).
- **비교 한계(중요)**: 이 수치는 세션 전체라 "BE 트랙만"·"오케스트레이션만"으로 떼어낼 수 없고, §3.1의 itsvff 호출별 합계는 캐시 분해가 없어 1:1 head-to-head가 거칠다. 그래도 시사점은 분명 — 긴 컨텍스트의 Opus 메인 스레드는 cache_read 누적으로 비싸지며($46의 절반가량이 cache_read), 설계·리뷰를 Sonnet+VFF의 가벼운 별도 컨텍스트로 떼어내면 그만큼 Opus 메인의 캐시 누적 증가를 늦춘다.

## 4. 정성 비교

**설계·분석 품질 — 대등.** Sonnet+VFF가 BE 계약 갭 4건을 능동 발굴(risk_level 자유문자열, signals symbol 부재, prices 인증 정책, watchlist brief DTO)해 Opus에 조율 요청했고, 일봉 `date` 오프바이원을 설계 단계에서 선제 차단(`new Date` 금지 규칙화)했다. 범위 완결성 판정(추가 스캐폴딩 vs 재정렬)도 정확. Opus급 산출물.

**안전성 — Sonnet+VFF가 더 보수적.** itsvff는 코디네이터(Opus) 중계 승인을 사용자 직접 확인으로 인정하지 않아 `codex exec` 트리거·커밋·push·PR을 2회 거부했다. Opus는 같은 외부 작업을 자율 권한으로 진행(단 GitHub 이슈 자동 생성은 분류기가 차단 → 명시 승인 후 진행).

**리뷰 꼼꼼함 — 충분.** FE#47 리뷰에서 5개 초점 전부 검증하고 경미 갭 2건(Signal.symbol 빈문자열 초기화 / parseDecimal undefined 메시지)을 잡아내며 "머지 가능" 판정.

## 5. 비용 분석

단가(per 1M tokens): Sonnet 4.6 = 입력 $3 / 출력 $15, Opus 4.8 = 입력 $5 / 출력 $25. (Codex는 별도 구독 예산.)

- 설계·리뷰 같은 **인지 작업을 Sonnet 단가로** 돌리면 동일 작업 대비 입력·출력 모두 약 40% 저렴.
- 또한 그 작업을 **별도 컨텍스트(서브에이전트)로 분리**하면 Opus 메인 세션의 cache_read 누적(§3.3에서 비용의 약 절반)을 늦추는 2차 절감이 있다.
- 단 §6 권한 경계 마찰로 **약 157k 토큰이 거부 턴에 낭비**됐다. 3자 분업을 처음부터 적용(외부 작업을 itsvff에 아예 안 맡김)했다면 이 낭비는 0에 수렴.
- 구현 비용은 양 트랙 동일(같은 Codex): BE 201k / FE 129k.

## 6. 핵심 발견

1. **VFF 서브에이전트의 권한 경계(구조적)**: 이 하니스는 서브에이전트에 사용자 메시지를 직접 전달하지 못하고 코디네이터(Opus) 중계만 가능하다. itsvff는 중계 승인을 원천 불신하여 외부/비가역 작업(codex 트리거·커밋·push·PR)을 거부한다. → **Sonnet+VFF 단독으로 외부 오케스트레이션은 이 구성에서 불가능.** 외부 실행은 Opus가 맡고 itsvff엔 설계·리뷰만 주는 3자 분업이 해법.
2. **codex exec 백그라운드 hang**: codex exec를 백그라운드/파이프로 띄우면 stdin EOF 대기로 무한 hang("Reading additional input from stdin..."). CPU 0.2초에서 정지·세션로그 부재가 증상. `< /dev/null`로 해결. (오진 주의: 3시간짜리 좀비 codex의 SQLite 공유락을 의심했으나, 좀비 생존 중에도 stdin 차단 재실행은 정상 진행 → SQLite 동시접근은 범인 아님.)

## 7. 결론·권고

- "Sonnet+VFF가 Opus를 완전 대체"는 이 하니스에선 **불가**(외부 작업 권한 경계).
- 그러나 **설계·리뷰의 인지 품질은 Opus에 필적**하며 그 부분을 Sonnet 단가로 처리 가능.
- 따라서 권고 모델 = **Opus(오케스트레이터·외부 실행) + Sonnet+VFF(설계·리뷰) + Codex(구현)** 3자 분업. 외부 작업은 처음부터 Opus에 두어 거부 마찰을 제거할 것.

## 8. 산출물 링크

- BE#97: `JongEunLee310/project_stock` PR #111(CI pass, 260 tests). 설계 `docs/designs/price-series-api.md`, 리뷰 `docs/reviews/pr-111.md`.
- FE#47: `JongEunLee310/project_stock_frontend` PR #54(리뷰 머지가능). 설계 `docs/designs/47-domain-realignment.md`, 리뷰 `docs/reviews/pr-54.md`.
- 후속 이슈: BE #112 (signals `?expand=asset`).
