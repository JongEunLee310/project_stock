# BE 설계: 클라우드 LLM 자유 텍스트 민감정보 마스킹 — 이슈 #456

상태: **설계 초안(Draft)** — 2026-10-12. 결정은 ADR-019(ADR-009 보완). 에픽 #438. 적용 대상은
리서치 Q&A(#442)와 판단 기록 작성 보조(#356)다.

이 문서는 자유 텍스트 마스킹의 범주, 판정 규칙, 게이트웨이 배선, 계약 변경을 스켈레톤 수준으로
확정한다. 정규식과 구현 코드는 담지 않는다. 출처가 없는 경계값은 "가정"으로 표기했다.

## 배경

- 클라우드로 나가는 사용자 작성 자유 텍스트는 두 곳이다.
  - `ResearchQASnapshot.question`(`app/adapters/llm/privacy.py`)
  - `DecisionAssistSnapshot.thesis`·`rationale`·`memo`(`app/adapters/llm/privacy.py:53-61`)
- 클라우드 경로는 `LLMGateway.complete_json`(`app/adapters/llm/gateway.py:59`)과
  `_verify_with_cloud`(`gateway.py:177`) 두 곳에서 `PrivacyGate.guard`를 거친다. 사전 escalation
  판단(`gateway.py:69-90`)도 `guard`를 호출한다. 응답 캐시 키는 `guard` 결과로 만든다.
- `PrivacyGate.guard`는 지금 타입과 민감도만 검사하고 payload를 그대로 돌려준다
  (`privacy.py:456-470`).

## 1. 범주와 자리표시자

`MaskCategory`(`app/adapters/llm/masking.py`, `str` Enum, 값은 영어 `UPPER_SNAKE` — ADR-002 wire enum
컨벤션)

| 값 | 대상 | 적용 조건 | 자리표시자 |
|---|---|---|---|
| `EMAIL` | 이메일 주소 | 항상 | `[이메일]` |
| `PHONE` | 국내 휴대폰·유선 번호, 국제 형식 번호 | 항상 | `[전화번호]` |
| `RESIDENT_ID` | 주민등록번호 형식(6자리-7자리) | 항상 | `[주민등록번호]` |
| `CARD` | 카드번호 형식(4자리×4, 구분자 허용) | 항상 | `[카드번호]` |
| `ACCOUNT` | 계좌번호 형식(숫자와 하이픈 10~16자리, 가정) | "계좌" 등 표지 근처일 때, 또는 위 형식에 해당하지 않는 긴 숫자열 | `[계좌번호]` |
| `QUANTITY` | 주식 수량(예: 300주, 1,000 shares) | 개인 맥락 표지와 같은 문장에 있을 때 | `[수량]` |
| `AMOUNT` | 금액·평단가(예: 7만 원, 5천만원, $20,000, 1.2억) | 개인 맥락 표지와 같은 문장에 있을 때 | `[금액]` |

판정 순서는 `RESIDENT_ID` → `CARD` → `PHONE` → `EMAIL` → `ACCOUNT` → `QUANTITY` → `AMOUNT`다(가정).
형식이 겹치는 긴 숫자열을 더 구체적인 범주부터 잡기 위해서다.

## 2. 개인 맥락 판정

`QUANTITY`와 `AMOUNT`는 공개 사실(계약 규모, 매출, 자사주 소각 수량)에도 나오므로 개인 맥락일 때만
가린다.

- 판정 단위는 문장이다(마침표, 물음표, 느낌표, 줄바꿈으로 나눔, 가정).
- 같은 문장 안에 개인 맥락 표지가 하나라도 있으면 그 문장의 수량·금액을 가린다.
- 개인 맥락 표지(가정, 테스트로 고정)
  - 한국어: 내, 제, 저의, 나의, 우리, 보유, 들고 있, 매수, 매입, 매도, 샀, 팔았, 사 둔, 평단, 평균단가,
    투자했, 넣었, 물려, 손절, 익절, 계좌, 예수금, 원금
  - 영어: my, mine, I have, I hold, I bought, I sold, I own, my position, cost basis, average cost

## 3. 가리지 않는 표현(오탐 방지)

다음은 개인 맥락 표지가 있어도 가리지 않는다. 테스트에 고정 사례로 둔다.

- 퍼센트: 20%, -15.3%, 3%p
- 배수와 비율: PER 30배, PBR 1.2배, 2배 레버리지
- 기간과 날짜: 3분기, 2026년, 52주 신고가, 5년
- 지수·가격 수준 언급 중 개인 맥락이 없는 문장: "코스피 2,600", "엔비디아 시총 4조 달러"
- 종목 코드: 005930, NVDA

## 4. 컴포넌트

### 4.1 `app/adapters/llm/masking.py`

- `MaskCategory` — §1
- `MaskResult`(frozen dataclass): `text: str`, `categories: frozenset[MaskCategory]`
- `mask_sensitive_text(text: str) -> MaskResult` — §1~§3 규칙을 적용한 순수 함수. 빈 문자열과 `None`
  처리는 호출부가 아니라 이 함수의 입력 타입(`str`)에 맞춰 상위에서 거른다.

### 4.2 `CloudSafePayload` 선언

- `CloudSafePayload`에 `free_text_fields: ClassVar[tuple[str, ...]] = ()`를 추가한다.
- `ResearchQASnapshot.free_text_fields = ("question",)`
- `DecisionAssistSnapshot.free_text_fields = ("thesis", "rationale", "memo")`
- 선언된 필드는 `str | None`이어야 한다. 정의 시점이나 첫 사용 시점에 검증해 잘못된 선언(없는 필드,
  다른 타입)을 오류로 만든다.

### 4.3 `PrivacyGate`

- `guard(payload) -> CloudSafePayload` — 기존 검사(타입, 민감도)는 그대로다.
- `mask(payload: CloudSafePayload) -> tuple[CloudSafePayload, frozenset[MaskCategory]]` — 새 메서드.
  `free_text_fields`의 값에 `mask_sensitive_text`를 적용한 사본(`model_copy(update=...)`)과 가린 범주를
  돌려준다. 선언이 없으면 원본과 빈 집합을 돌려준다.
- 원문과 자리표시자의 대응은 저장하거나 로그에 남기지 않는다. 가린 범주 이름만 info 로그로 남긴다.

### 4.4 `LLMGateway`

- 클라우드로 가는 모든 경로에서 `guard` 다음에 `mask`를 적용하고, 그 결과만 client와 캐시 키에 쓴다.
  - 직접 클라우드 호출(`complete_json`)
  - 로컬 응답 후 클라우드 검증(`_verify_with_cloud`)
  - 사전 escalation 판단의 `guard` 호출은 판정용이라 변경하지 않는다. 실제 전송은 위 두 경로를 탄다.
- 로컬로 라우팅된 호출은 마스킹하지 않는다(ADR-019 §3).
- `LLMCompletionResult.masked_categories: frozenset[MaskCategory] = frozenset()`를 추가한다. 캐시 적중
  경로에서도 같은 값을 채운다(마스킹은 캐시 조회 전에 계산).

## 5. 계약 변경

두 API 모두 응답 필드를 추가만 한다.

| API | 응답 필드 | 의미 |
|---|---|---|
| `POST /api/v1/assets/{asset_id}/research-qa` | `masked_categories: list[MaskCategory]` | 클라우드 전송 시 가린 범주. LLM을 호출하지 않았으면(근거 0건) 빈 목록 |
| `POST /api/v1/decision-logs/assist` | `masked_categories: list[MaskCategory]` | 같음. LLM 호출이 실패해 빈 제안을 돌려줄 때는 빈 목록 |

- 목록은 `MaskCategory` 선언 순서로 정렬한다.
- Obsidian 노트에는 원문 질문을 그대로 쓴다(로컬). 노트 frontmatter에 `masked_categories`를 함께 남겨
  어떤 정보가 클라우드에 가려졌는지 기록한다.
- 질문 임베딩(로컬 Ollama)은 원문을 그대로 쓴다.

## 6. 테스트 전략

| 대상 | 핵심 검증 |
|---|---|
| `mask_sensitive_text` | 범주별 한국어·영어 양성 사례, §3 음성 사례, 개인 맥락 유무에 따른 수량·금액 판정, 한 문장 여러 범주, 문장 경계, 판정 순서 |
| `free_text_fields` 선언 검증 | 없는 필드·비문자열 필드 선언 시 오류 |
| `PrivacyGate.mask` | 선언 필드만 바뀌고 다른 필드(공개 근거 발췌 등)는 그대로 |
| `LLMGateway` | 직접 클라우드·클라우드 검증 경로에서 client가 받은 메시지에 원문이 없음, 로컬 경로는 원문 유지, 캐시 키가 마스킹 payload 기준, 캐시 적중 시에도 `masked_categories` 반환 |
| Q&A API | 질문의 개인 금액이 LLM 메시지에서 가려지고 응답 `masked_categories`에 `AMOUNT`, 공개 금액 질문은 가려지지 않음, 근거 0건이면 빈 목록, Obsidian 노트에는 원문 |
| Decision Assist API | 메모의 연락처·수량이 가려지고 응답에 범주 표시 |

픽스처 문장은 실제 사용 문장 형태로 쓴다(예: "삼성전자 300주를 평단 7만 원에 샀는데 지금 리스크는?",
"애플-브로드컴 300억 달러 계약 내용은?").

## 7. 범위 밖

- 사람 이름, 주소 등 규칙으로 잡기 어려운 정보(로컬 LLM 판별은 ADR-008 Phase 2와 함께 검토)
- 구조화 projection의 기존 화이트리스트 변경
- FE 안내 UI(`project_stock_frontend#308`, 판단 기록 작성 보조 화면)

## 8. ADR

ADR-019(ADR-009 보완)를 이 PR에서 추가한다. 프라이버시 경계 변경이므로 머지 전 사람 리뷰가 필요하다.
