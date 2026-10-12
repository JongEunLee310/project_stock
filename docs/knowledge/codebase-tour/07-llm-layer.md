# 07. LLM 층

대상 파일: `app/adapters/llm/*`, `app/adapters/llm/prompts/*`

06단계의 시장 어댑터가 `base` / `mock` / `real` 삼각 구조였다면, LLM은 그 위에 **게이트웨이**가
얹힙니다. 이유는 LLM 호출에 다른 어댑터에 없는 관심사가 붙기 때문입니다 — 어느 모델로 보낼지,
개인정보를 보내도 되는지, 비용을 얼마나 썼는지, 응답을 믿을 수 있는지.

```text
app/adapters/llm/
  base.py        LLMClient 인터페이스
  openai.py      클라우드 구현
  local.py       로컬 구현
  mock.py        가짜 구현
  gateway.py     ★ 위 4개를 감싸며 정책을 적용하는 진입점
  router.py      태스크 → 프로바이더 매핑
  privacy.py     클라우드 전송 경계 (479줄, 이 층에서 가장 큼)
  budget.py      일일 호출 예산
  cache.py       응답 캐시
  escalation.py  로컬 → 클라우드 승격 정책
  schema.py      응답 JSON 스키마
  types.py       요청·응답 타입, enum
  exceptions.py  예외 계층
  prompts/       태스크별 시스템 프롬프트
```

## base.py — 클라이언트 인터페이스

```python
class LLMClient(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def complete(self, messages: list[LLMMessage], timeout: float | None = None) -> str: ...

    @abstractmethod
    def complete_json(
        self, messages: list[LLMMessage], schema: type[BaseModel], timeout: float | None = None
    ) -> dict[str, Any]: ...
```

`@property` + `@abstractmethod`를 겹쳐 **추상 프로퍼티**를 만듭니다. 순서가 중요한데
`@property`가 바깥에 와야 합니다. 이 두 값은 "어느 모델이 이 답을 만들었는가"를 결과에 남기기
위한 것으로, 나중에 응답 품질을 모델별로 비교할 수 있게 합니다.

메서드가 두 개인 것이 설계의 핵심입니다.

- `complete` — 자유 텍스트
- `complete_json` — **스키마를 인자로 받아** JSON 객체를 반환

이 프로젝트는 사실상 `complete_json`만 씁니다. LLM 응답을 화면에 그대로 뿌리지 않고 **구조화된
필드로 받아 도메인 스키마에 채워 넣기** 때문입니다.

`LLMMessage(role, content)`는 OpenAI의 메시지 형식을 그대로 본떴지만 **표준 dataclass**입니다.
06단계와 같은 원칙 — 외부 라이브러리 타입이 어댑터 밖으로 나가지 않습니다.

## types.py — 요청·응답의 어휘

```python
class LLMTaskType(str, Enum):
    NEWS_SUMMARY = "NEWS_SUMMARY"
    THESIS_CONFLICT = "THESIS_CONFLICT"
    ...
    AGENT = "AGENT"
```

**11개 태스크 타입이 이 시스템이 LLM에게 시키는 일의 전체 목록**입니다. 라우팅·캐시 키·로그가
모두 이 값을 기준으로 갈리므로, 새 LLM 기능을 추가하려면 여기서 시작합니다.

```python
class SensitivityLevel(str, Enum):
    RAW = "RAW"            # 원본 (보유 수량, 금액)
    SEMI = "SEMI"          # 부분 가공
    AGGREGATED = "AGGREGATED"  # 집계·구간화
    PUBLIC = "PUBLIC"      # 공개 정보
```

**민감도 4단계**가 이 층의 중심 개념입니다. 뒤의 `PrivacyGate`가 이 값만 보고 클라우드 전송을
허용할지 결정합니다.

```python
@dataclass(frozen=True)
class LLMRequest:
    task_type: LLMTaskType
    system_prompt: str
    sensitivity_level: SensitivityLevel
    risk_level: RiskLevel
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_schema: type[BaseModel] | None = None
    ...
```

`LLMRequest`/`LLMResponse`는 완결된 요청·응답 모델이지만, **현재 `LLMGateway.complete_json`은 이
타입을 쓰지 않고 인자를 개별로 받습니다.** 설계가 먼저 서고 게이트웨이는 필요한 만큼만 구현된
상태입니다. 코드를 읽을 때 "정의됐지만 아직 쓰이지 않는 타입"으로 분류해 두면 됩니다.

`LLMResponse`의 `validation_status`, `token_usage`, `cache_hit` 같은 필드는 향후 사용량·품질
추적을 위한 자리입니다.

## router.py — 태스크를 프로바이더에 매핑

```python
@dataclass(frozen=True)
class TaskRoute:
    launch: str          # 지금 쓰는 것
    future_primary: str  # 앞으로 쓸 것

LLM_TASK_ROUTES: dict[LLMTaskType, TaskRoute] = {
    LLMTaskType.NEWS_SUMMARY: TaskRoute(launch="cloud", future_primary="local"),
    LLMTaskType.THESIS_CONFLICT: TaskRoute(launch="cloud", future_primary="cloud"),
    ...
}

    def resolve(self, task_type: LLMTaskType) -> str:
        route = self.routes.get(task_type)
        if route is None:
            raise LLMRoutingError(f"LLM task route is not defined: {task_type!r}")
        return route.launch
```

**필드가 두 개인 것이 이 파일의 전부**입니다. 현재는 전부 `launch="cloud"`이므로 실제 동작은
"모두 클라우드"인데, `future_primary`에 **로컬 모델로 옮길 계획이 데이터로 기록**되어 있습니다.

`future_primary="cloud"`로 남은 것은 `THESIS_CONFLICT`, `PORTFOLIO_BRIEFING`, `AGENT` 세
개입니다. 추론 난도가 높거나 결과의 파급이 큰 태스크는 계속 클라우드에 둔다는 판단입니다.

문서 대신 코드에 계획을 담은 형태이며, `resolve`는 `launch`만 읽으므로 **현재 동작에는 영향이
없습니다.** 로컬 전환 시 `route.future_primary`로 한 글자만 바꾸면 되는 구조입니다.

라우트가 없으면 `LLMRoutingError`를 던집니다. 새 `LLMTaskType`을 추가하고 라우트 등록을 잊으면
호출 시점에 명확히 터집니다.

## privacy.py — 클라우드 전송 경계 (이 층의 핵심)

479줄로 LLM 층에서 가장 큰 파일이며, 이 프로젝트가 가장 신경 쓴 부분입니다.

### CloudSafePayload — 타입으로 강제하는 경계

```python
class CloudSafePayload(BaseModel):
    sensitivity: ClassVar[SensitivityLevel]

    model_config = ConfigDict(frozen=True)

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
```

`ClassVar`로 선언한 `sensitivity`는 **인스턴스 필드가 아니라 클래스 속성**입니다. 즉 민감도는
데이터가 아니라 **타입에 붙습니다.** 하위 클래스가 각자 값을 정합니다.

```python
class NewsSummarySnapshot(CloudSafePayload):
    sensitivity = SensitivityLevel.PUBLIC
    ...

class PortfolioConcentrationSnapshot(CloudSafePayload):
    sensitivity = SensitivityLevel.AGGREGATED
    ...
```

`frozen=True`라 만들어진 뒤 수정할 수 없습니다. 게이트를 통과한 payload를 나중에 몰래 바꾸는 경로를
막습니다.

`model_dump(mode="json")`은 `Decimal`·`datetime`을 JSON 호환 값으로 변환합니다. 06단계의 캐시가
타입 태그를 붙여 보존했던 것과 대비되는데, **LLM에 보낼 때는 복원이 필요 없으므로** 단순 변환으로
충분합니다.

### PrivacyGate — 실제 검문

```python
class PrivacyGate:
    CLOUD_ALLOWED: ClassVar[frozenset[SensitivityLevel]] = frozenset(
        {SensitivityLevel.AGGREGATED, SensitivityLevel.PUBLIC}
    )

    def guard(self, payload: object) -> CloudSafePayload:
        if not isinstance(payload, CloudSafePayload):
            raise CloudBoundaryViolationError("payload is not CloudSafe")
        if payload.sensitivity not in self.CLOUD_ALLOWED:
            raise CloudBoundaryViolationError(
                f"payload sensitivity is not allowed: {payload.sensitivity.value}"
            )
        return payload
```

**검문은 두 겹입니다.**

1. **타입 검사** — `CloudSafePayload`가 아니면 거부. 개발자가 dict를 그냥 넘기는 실수를 막습니다.
2. **민감도 검사** — `AGGREGATED`와 `PUBLIC`만 통과. `RAW`·`SEMI`는 클라우드로 나갈 수 없습니다.

`guard`의 인자 타입이 `CloudSafePayload`가 아니라 `object`인 것이 의도적입니다. 타입 힌트로
좁혀두면 mypy가 잡아주지만 런타임 검사는 사라집니다. 여기서는 **런타임에도 반드시 확인**해야
하므로 넓게 받아 `isinstance`로 검사합니다.

`frozenset`을 클래스 변수로 둔 것은 실수로 허용 목록에 값을 추가하는 경로를 막기 위한 것입니다.

### 구간화 — 민감한 값을 등급으로 바꾸기

경계를 통과시키는 실제 기법이 변환 함수들에 있습니다.

```python
POSITION_COUNT_SMALL_MAX = 5
POSITION_COUNT_MEDIUM_MAX = 15
LOW_SHARE_MAX = Decimal("0.25")
MEDIUM_SHARE_MAX = Decimal("0.40")

def _position_count_band(position_count: int) -> str:
    if position_count <= POSITION_COUNT_SMALL_MAX:
        return "1-5"
    if position_count <= POSITION_COUNT_MEDIUM_MAX:
        return "6-15"
    return "16+"

def _share_band(share: Decimal) -> str:
    if share < LOW_SHARE_MAX:
        return "0-25%"
    if share < MEDIUM_SHARE_MAX:
        return "25-40%"
    return "40%+"
```

```python
def to_concentration_snapshot(portfolio: Portfolio, positions: Sequence[Position]) -> PortfolioConcentrationSnapshot:
    ...
    return PortfolioConcentrationSnapshot(
        position_count_band=_position_count_band(len(positions)),
        largest_position_band=_share_band(largest_position_share),
        cash_band=_share_band(cash_share),
        is_concentrated=largest_position_share > portfolio.concentration_threshold,
    )
```

**정확한 값을 계산은 하되, 밖으로 내보내는 것은 구간 문자열입니다.** "현금 1,247만원"이 아니라
`"25-40%"`가, "12종목 보유"가 아니라 `"6-15"`가 나갑니다.

LLM은 "현금 비중이 25~40% 구간이고 집중도가 높다"만 알아도 유용한 조언을 만들 수 있습니다.
**분석에 필요한 최소 정보만 보내는 것**이 이 설계의 요지입니다.

`is_concentrated`가 불린인 것도 같은 맥락입니다. 임계값 비교는 서버가 하고 결과만 보냅니다.

이 프로젝트가 파생 뷰 타입을 `DTO`가 아니라 **`Projection`**(`ContextBundleSignalProjection` 등)으로
부르는 규칙도 여기서 일관되게 지켜집니다.

## gateway.py — 정책을 조립하는 진입점

`complete_json` 한 메서드에 6단계가 순서대로 들어 있습니다.

```text
1. router.resolve(task_type)          어느 프로바이더로?
2. escalation.should_escalate_before  선제 승격이 필요한가?
3. privacy_gate.guard(payload)        클라우드로 보내도 되는가?
4. response_cache.lookup              캐시에 있는가?
5. call_budget.consume()              예산이 남았는가?
6. client.complete_json               실제 호출
7. escalation.should_verify_after     결과를 클라우드로 재검증할까?
```

### 순서가 곧 정책이다

```python
        safe_payload = self.privacy_gate.guard(payload) if provider == CLOUD else payload
        cache_key: str | None = None
        if provider == CLOUD and self.response_cache is not None:
            cache_key = self.response_cache.build_key(...)
            cached_completion = self.response_cache.lookup(cache_key)
            if cached_completion is not None:
                return LLMCompletionResult(..., cached=True, escalated=escalated)

        if provider == CLOUD and self.call_budget is not None:
            self.call_budget.consume()
```

**개인정보 검문 → 캐시 조회 → 예산 차감 → 호출** 순서가 정확합니다.

- 검문이 캐시보다 먼저인 이유: 캐시 키를 만들려면 payload를 봐야 하는데, 나가면 안 될 데이터로
  키를 만드는 것 자체가 이미 경계를 넘은 것입니다.
- 예산 차감이 캐시 뒤인 이유: **캐시 적중은 외부 호출이 아니므로 예산을 쓰지 않습니다.**
- 세 정책 모두 `provider == CLOUD`일 때만 적용됩니다. 로컬 모델은 개인정보 유출도, 비용도 없기
  때문입니다.

### 정책이 모두 선택적이다

```python
    def __init__(
        self,
        clients: Mapping[str, LLMClient],
        router: LLMRouter | None = None,
        privacy_gate: PrivacyGate | None = None,
        timeout_seconds: float | None = None,
        call_budget: DailyCallBudget | None = None,
        response_cache: LLMResponseCache | None = None,
        escalation_policy: EscalationPolicy | None = None,
    ) -> None:
        self.router = LLMRouter() if router is None else router
        self.privacy_gate = PrivacyGate() if privacy_gate is None else privacy_gate
```

`router`와 `privacy_gate`는 **`None`이면 기본 인스턴스를 만듭니다** — 끌 수 없습니다.
`call_budget`·`response_cache`·`escalation_policy`는 `None`이면 그 단계를 통째로 건너뜁니다.

**안전에 관한 것은 항상 켜져 있고, 최적화에 관한 것은 선택**이라는 구분이 생성자에 드러납니다.
06단계에서 본 팩토리가 설정에 따라 뒤의 세 개를 만들거나 `None`으로 둡니다.

### 에스컬레이션 — 로컬 결과를 클라우드로 재검증

```python
    def should_escalate_before(self, signal: EscalationSignal, resolved_provider: str) -> bool:
        if resolved_provider != LOCAL:
            return False
        return (signal.risk_level == RiskLevel.HIGH or signal.loss_spike
                or signal.news_sentiment_swing or signal.event_flag or signal.trade_question)
```

**사전 승격** — 로컬로 갈 예정이었는데 상황이 위중하면(고위험, 손실 급증, 뉴스 심리 급변, 이벤트,
매매 질문) 처음부터 클라우드로 보냅니다.

```python
    def should_verify_after(self, output: dict[str, Any], schema: type[BaseModel], first_provider: str) -> bool:
        if first_provider == CLOUD:
            return False
        confidence = output.get("confidence")
        if (self.confidence_threshold is not None
                and not isinstance(confidence, bool)
                and isinstance(confidence, int | float)
                and confidence < self.confidence_threshold):
            return True
        try:
            schema.model_validate(output)
        except ValidationError:
            return True
        return False
```

**사후 검증** — 로컬 결과의 자신감이 낮거나 스키마를 만족하지 못하면 클라우드로 다시 물어봅니다.

`not isinstance(confidence, bool)` 검사가 미묘합니다. 파이썬에서 `bool`은 `int`의 하위 타입이라
`isinstance(True, int)`가 참입니다. 이 검사가 없으면 `confidence: false`가 `0 < threshold`로
평가되어 "신뢰도 0"으로 오독됩니다. 순서도 중요해서, `bool` 배제가 숫자 검사보다 앞에 와야
합니다. 뒤에 두면 이미 통과한 뒤라 의미가 없습니다.

의도는 "불리언은 신뢰도 점수가 아니므로 숫자로 재해석하지 말고 다음 단계인 스키마 검증에
판단을 넘겨라"입니다.

### 그런데 넘긴 곳이 막아 주지 않는다

실제 스키마 `LLMAnalysisResult`로 끝까지 돌려 보면 결과가 이렇습니다(임계값 0.7).

| `confidence` | 재검증 여부 | 기대 |
| --- | --- | --- |
| `0.0` | True | True |
| `0.42` | True | True |
| `0.95` | False | False |
| `False` | **False** | **True** |

`0.0`은 재검증하는데 `False`는 하지 않습니다. Pydantic이 비엄격 모드에서 `bool`을 `float`으로
강제 변환하기 때문입니다(`False` → `0.0`). `Field(ge=0.0, le=1.0)` 제약도 통과하므로
`schema.model_validate(output)`이 성공하고, 그대로 `return False`가 됩니다.

**1단계가 판단을 미루고 2단계가 문제없다고 판정하는 조합**이라 어느 쪽도 걸러내지 못합니다.
가드의 의도는 옳지만 방어가 절반만 이루어진 상태입니다. 이슈 #432로 등록했습니다.

### 클라우드는 요청당 한 번만

두 정책 모두 첫 공급자가 클라우드면 즉시 `False`입니다.

| 메서드 | 시점 | 가드 |
| --- | --- | --- |
| `should_escalate_before` | 호출 **전** — 위험 신호를 보고 처음부터 클라우드로 | `resolved_provider != LOCAL` |
| `should_verify_after` | 호출 **후** — 결과가 미덥지 않으면 클라우드로 재확인 | `first_provider == CLOUD` |

에스컬레이션의 정의가 "로컬이 미덥지 않으니 클라우드에 다시 물어본다"이므로, 첫 호출이 이미
클라우드였다면 같은 모델에 같은 질문을 두 번 하는 셈입니다. 얻는 것 없이 지연이 늘고, 일일
호출 예산도 두 번 차감됩니다(`_verify_with_cloud`가 `consume()`을 다시 호출).

두 가드 덕에 클라우드 개입이 **요청당 최대 한 번**으로 제한됩니다.

### 실패해도 진행한다

```python
            try:
                self.privacy_gate.guard(payload)
            except CloudBoundaryViolationError:
                logger.warning("llm escalation provider override skipped: ... reason=cloud_boundary",
                               exc_info=True)
            else:
                provider = CLOUD
                escalated = True
```

**승격하려 했는데 개인정보 경계에 걸리면 승격을 포기하고 로컬로 진행**합니다. 경계가 승격 정책보다
우선한다는 뜻이며, 예외를 던져 요청 전체를 실패시키지 않습니다.

`try/except/else` 구조에서 `else`는 예외가 없을 때만 실행됩니다. `try` 블록을 최소화해 의도를
명확히 하는 파이썬 관용구입니다.

```python
            if cloud_client is None:
                # 재호출이 수행되지 않았으므로 escalated로 표시하지 않는다.
                logger.warning("llm escalation cloud verification skipped: ... reason=cloud_client_missing", ...)
```

이 한글 주석이 `escalated` 플래그의 의미를 정확히 정의합니다 — **"승격을 시도했다"가 아니라
"실제로 클라우드를 호출했다"**. `_CloudVerificationResult.attempted`가 그 구분을 나릅니다.

로그 메시지가 `reason=cloud_boundary`, `reason=schema_validation`, `reason=exception`처럼
**구조화된 형태**인 점도 눈여겨볼 만합니다. 나중에 로그를 집계해 "왜 승격이 실패했는가"를 셀 수
있습니다.

## budget.py — 24줄짜리 비용 방어

```python
class RedisCounter(Protocol):
    def incr(self, name: str) -> int: ...
    def expire(self, name: str, time: int) -> object: ...


class DailyCallBudget:
    def consume(self) -> None:
        key = f"llm:cloud_calls:{datetime.now(UTC).strftime('%Y%m%d')}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, 2 * 24 * 60 * 60)
        if count > self.limit:
            raise LLMBudgetExceededError("daily cloud LLM call limit exceeded")
```

**`Protocol`을 쓴 것이 이 파일에서 배울 점입니다.** `redis.Redis` 타입을 직접 요구하면 테스트에서
진짜 Redis가 필요합니다. `Protocol`은 "`incr`과 `expire` 메서드만 있으면 무엇이든 좋다"는
구조적 타이핑이라, 테스트에서 dict 기반 가짜를 넘길 수 있습니다. ABC 상속과 달리 **가짜 쪽이
아무것도 상속하지 않아도** 됩니다.

`incr`은 원자적이므로 동시 요청에서도 카운트가 정확합니다. `count == 1`일 때만 TTL을 거는 것은
**그날의 첫 호출에서만 만료를 설정**하는 관용구입니다. 매번 `expire`를 부르면 만료가 계속 밀립니다.

TTL이 하루가 아니라 이틀(`2 * 24 * 60 * 60`)인 이유는 타임존 경계와 시계 오차에 여유를 두기
위한 것입니다. 키에 날짜가 들어가므로 자정이 지나면 자연히 새 카운터가 시작됩니다.

`count > self.limit`에서 **이미 증가시킨 뒤 검사**하므로, 한도를 넘긴 호출도 카운트에 남습니다.
차단 이후에도 시도 횟수를 알 수 있게 하는 선택입니다.

## cache.py — 응답 캐시

```python
# Bump when prompt assembly, provider schema instructions, or cache envelope changes.
CACHE_SCHEMA_VERSION = "v1"
```

**캐시 스키마 버전**입니다. 프롬프트 조립 방식이 바뀌면 예전 캐시는 다른 조건의 결과이므로 쓰면
안 됩니다. 이 문자열을 올리면 모든 키가 바뀌어 자연스럽게 무효화됩니다. 주석이 "언제 올려야
하는가"를 명시한 것이 좋은 사례입니다.

```python
    def build_key(self, task_type, payload, system_prompt, model_name, schema) -> str:
        digest_material = json.dumps(
            [payload.as_payload(), system_prompt, model_name, schema.model_json_schema()],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(digest_material.encode("utf-8")).hexdigest()
        date_key = datetime.now(UTC).strftime("%Y%m%d")
        return f"llm:cache:{CACHE_SCHEMA_VERSION}:{task_type.value}:{date_key}:{digest}"
```

키에 **결과를 바꿀 수 있는 모든 것**이 들어갑니다 — payload, 시스템 프롬프트, 모델 이름, 응답
스키마. 하나라도 다르면 다른 키가 되므로 잘못된 캐시 재사용이 없습니다.

`date_key`가 들어가는 것이 이 도메인 특유의 처리입니다. **주식 분석은 어제 답이 오늘 유효하지
않습니다.** TTL과 무관하게 날짜가 바뀌면 캐시가 갈립니다.

`sort_keys=True` + `separators`는 05·06단계의 해시 안정화와 같은 이유입니다.

## openai.py — 실제 클라우드 클라이언트

### 스키마 지시를 프로바이더가 소유한다

```python
        # Keep the schema instruction provider-owned by always prepending it.
        schema_message = LLMMessage(
            role="system",
            content=("Return only a valid JSON object matching this JSON Schema: "
                     f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"),
        )
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=_to_openai_messages([schema_message, *messages]),
            response_format=ResponseFormatJSONObject(type="json_object"),
            timeout=timeout,
        )
```

**Pydantic 모델에서 JSON Schema를 자동 생성해 프롬프트 맨 앞에 붙입니다.** `schema.model_json_schema()`
한 줄로 필드 이름·타입·필수 여부가 전부 전달됩니다. `LLMAnalysisResult`의 경우 1051자짜리
JSON이 만들어집니다.

| 파이썬 선언 | JSON Schema |
| --- | --- |
| `summary: str` | `"type": "string"` |
| `reasons: list[str]` | `"type": "array", "items": {"type": "string"}` |
| `SuggestedAction` (Enum) | `"enum": ["buy_watch", "hold", "trim_watch", "avoid", "need_more_data"]` |
| `Field(ge=0.0, le=1.0)` | `"minimum": 0.0, "maximum": 1.0` |
| 기본값 없는 필드 | `"required": [...]` 에 포함 |

**enum 값까지 그대로 전달된다**는 점이 실질적 이점입니다. 손으로 적었다면 enum에 값을 추가할 때
프롬프트도 함께 고쳐야 하고, 빠뜨리면 모델이 새 값을 모릅니다.

주석의 "provider-owned"는 **출력 형식을 지시할 책임이 어댑터에 있다**는 뜻입니다. 형식을 강제하는
방법이 공급자마다 다르기 때문입니다.

| 관심사 | 담당 | 예 |
| --- | --- | --- |
| **무엇을** 물을 것인가 (내용) | `prompts/` — 도메인 | "너는 투자 분석 어시스턴트다", 한국어로 답하라 |
| **어떤 형식으로** 받을 것인가 | 어댑터 — 공급자별 | OpenAI는 `response_format=json_object` |

공급자를 바꾸면 그 어댑터가 자기 방식(네이티브 structured output, 문법 제약 디코딩 등)을 쓰고,
도메인 프롬프트는 손대지 않습니다. 06단계의 "외부 라이브러리 타입이 어댑터 밖으로 나가지 않는다"와
같은 원칙이 형식 지시에도 적용된 것입니다.

### 다만 실제로는 두 번 보내고 있다

`prompts/`의 빌더 4개도 같은 스키마를 넣고 있습니다.

```python
# app/adapters/llm/prompts/analysis.py:11-15
schema_json = json.dumps(LLMAnalysisResult.model_json_schema(), ensure_ascii=False)
return (
    "You are an investment analysis assistant. ... "
    f"JSON Schema: {schema_json}\n\n"      # ← 여기서 한 번
)
```

`openai.py`가 여기에 다시 붙이므로 OpenAI 호출 시 같은 JSON이 **두 번 전송**됩니다.

| 프롬프트 빌더 | 스키마 포함 |
| --- | --- |
| `analysis.py` · `decision_assist.py` · `news_summary.py` · `thesis_conflict.py` | 포함 |
| `dashboard_briefing.py` 외 6개 | 없음 |

양쪽 다 `model_json_schema()`를 부르므로 **불일치는 생기지 않습니다.** 스키마가 바뀌면 둘 다
따라가므로 위에서 말한 이점 자체는 유효합니다. 문제는 토큰 비용과, 같은 계층 안에서 방침이
갈려 있다는 점입니다. 스키마를 넣지 않는 6개 빌더 쪽이 오히려 "provider-owned" 원칙에
부합합니다. 이슈 #434로 등록했습니다.

`response_format={"type": "json_object"}`는 OpenAI API의 JSON 모드로, 모델이 반드시 파싱 가능한
JSON을 내도록 강제합니다. 프롬프트 지시(내용)와 API 옵션(형식) **두 겹으로 보장**합니다.

### 예외를 프로젝트 타입으로 변환

```python
        except openai.APITimeoutError as exc:
            logger.warning("provider call timed out", extra={"provider": "openai", "operation": operation})
            raise LLMTimeoutError("OpenAI request timed out") from exc
        except openai.OpenAIError as exc:
            raise LLMCallError("OpenAI request failed") from exc
```

06단계 원칙의 반복 — **외부 라이브러리 예외가 어댑터 밖으로 나가지 않습니다.** `openai.` 접두사가
붙은 타입이 도메인에 등장하지 않으므로, 프로바이더를 교체해도 호출부는 그대로입니다.

`extra={"provider": ..., "operation": ...}`의 두 키는 1단계 `JsonFormatter` 화이트리스트에 있어
운영 환경 JSON 로그에 실제로 나옵니다. 05단계의 `symbol` 같은 키가 누락되는 것과 대비됩니다.

### 응답 검증 3단계

```python
        content = completion.choices[0].message.content
        if not content:
            return {}
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMCallError("OpenAI returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMCallError("OpenAI returned JSON that is not an object")
        return parsed
```

빈 응답 → `{}`, 파싱 실패 → 예외, 배열이나 스칼라 → 예외. **LLM은 신뢰할 수 없는 입력원**이라는
전제로 다룹니다.

빈 응답만 예외가 아니라 `{}`인 것은 게이트웨이의 `if output and ...` 조건과 짝을 이룹니다 —
빈 결과는 캐시에 저장하지 않습니다.

여기서는 스키마 검증(`schema.model_validate`)까지 하지는 않습니다. 그 책임은 호출부(게이트웨이의
에스컬레이션, 도메인 service)에 있습니다.

## prompts/ — 태스크별 시스템 프롬프트

```python
WATCHLIST_OBSERVATION_SYSTEM_PROMPT = """
You generate concise watchlist observation notes for an investment monitoring tool.
Return only JSON matching ObservationsResult:
summary, items where each item has symbol and note.

Use the CloudSafe watchlist observation projection as the only source of facts.
Discuss each supplied symbol's status, PER, PEG, and daily change percent when
present, then summarize cross-watchlist patterns. Do not imply access to holdings,
share counts, market values, cost values, or absolute cash balances. Phrase guidance
as review support, not as an automatic buy, sell, or hold instruction.
""".strip() + "\n\n" + KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION
```

**프롬프트가 코드 파일의 모듈 상수**입니다. 문자열 템플릿 파일이나 DB가 아니라 파이썬 상수라,
git diff에 프롬프트 변경이 그대로 남고 리뷰 대상이 됩니다.

내용에 세 가지 방어가 들어 있습니다.

1. **출처 제한** — "CloudSafe projection을 유일한 사실 출처로 사용하라". 모델이 자기 지식으로
   지어내는 것을 막습니다.
2. **없는 정보 언급 금지** — "보유 수량·시장가치·절대 현금 잔액에 접근하는 것처럼 말하지 말라".
   `privacy.py`가 구간화해 보낸 것과 정확히 대응합니다. **데이터로 막고 프롬프트로 또 막는
   이중 방어**입니다.
3. **투자 조언 회피** — "매수·매도·보유 지시가 아니라 검토 지원으로 표현하라". 금융 도메인의
   규제 리스크를 프롬프트 수준에서 관리합니다.

```python
KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION = (
    "Write all natural-language field values (rationale, note, summary, "
    "headline, body, risk_checks, and similar fields) in Korean. Keep JSON keys, "
    "symbols, and enum values exactly as given."
)
```

11개 프롬프트가 모두 이 상수를 뒤에 붙입니다. **자연어는 한국어, JSON 키·심볼·enum 값은 원문
유지** — 후자를 명시하지 않으면 모델이 `"HIGH"`를 `"높음"`으로 번역해 Pydantic 검증이 실패합니다.
실제 사고를 겪고 추가한 흔적으로 읽힙니다.

프롬프트 본문이 영어인 것도 선택입니다. 모델의 지시 이해도가 영어에서 안정적이므로, 지시는
영어로 하고 출력 언어만 한국어로 지정합니다.

## schema.py — 응답 계약

```python
class ObservationsResult(BaseModel):
    summary: str
    items: list[ObservationItem]

class WatchlistEvaluationsResult(BaseModel):
    items: list[ItemEvaluationResult]
```

LLM이 돌려줘야 할 JSON 구조를 Pydantic 모델로 정의합니다. 이 모델이 세 곳에서 쓰입니다.

1. `openai.py`가 `model_json_schema()`로 변환해 **프롬프트에 삽입**
2. `escalation.py`가 `model_validate`로 **응답 검증**
3. 도메인 service가 결과를 파싱해 **응답 스키마로 변환**

**하나의 정의가 지시·검증·변환에 모두 쓰이는 것**이 이 설계의 핵심 이점입니다.

```python
class ItemEvaluationResult(BaseModel):
    symbol: str
    news_risk: str
    valuation_burden: str
    theme_heat: str
    ai_judgment: str
```

`news_risk`가 `str`인 점은 아쉬운 지점입니다. 04단계에서 본 `types.py`에 `NewsRisk` enum이 이미
있으므로 `news_risk: NewsRisk`로 두면 JSON Schema에 `enum: ["HIGH","MEDIUM","LOW"]`이 실려
모델이 값을 정확히 맞출 확률이 올라가고, 검증에서도 잘못된 값이 걸립니다.

## 전체 흐름 — 관심목록 AI 관찰 노트

```text
[엔드포인트] GET /watchlists/{id}/observations
    WatchlistObservationsService(db, get_llm_gateway())
        ↓
[팩토리]   settings.LLM_PROVIDER=cloud
           → LLMGateway({cloud: OpenAIClient, local: LocalLLMProvider},
                        call_budget, response_cache, escalation_policy)
        ↓
[도메인]   DB에서 관심목록·시세·시그널 조회
           → to_watchlist_observation_snapshot(...)  ← 구간화·필드 선별
           → WatchlistObservationSnapshot (CloudSafePayload, sensitivity=AGGREGATED)
        ↓
[게이트웨이] router.resolve(WATCHLIST_NOTE) → "cloud"
           → privacy_gate.guard()            AGGREGATED이므로 통과
           → response_cache.lookup()         (해시+날짜 키) 적중 시 여기서 반환
           → call_budget.consume()           일일 한도 초과 시 예외
           → messages = [system_prompt, json(payload)]
        ↓
[클라이언트] OpenAIClient.complete_json
           → JSON Schema 지시 메시지를 맨 앞에 추가
           → response_format=json_object로 호출
           → 파싱·타입 검사 → dict 반환
        ↓
[게이트웨이] cache.store() → escalation.should_verify_after()(cloud이므로 False)
           → LLMCompletionResult(output, provider, model_name)
        ↓
[도메인]   ObservationsResult로 검증 → WatchlistObservationsResponse로 변환
        ↓
[엔드포인트] success(...) → ApiResponse
```

## 이 단계에서 확인한 프로젝트 규칙

1. LLM 호출은 반드시 `LLMGateway`를 거친다. `LLMClient`를 도메인에서 직접 쓰지 않는다.
2. 클라우드로 보내는 데이터는 **반드시 `CloudSafePayload` 하위 타입**이어야 하고, 민감도는
   `AGGREGATED` 또는 `PUBLIC`이어야 한다.
3. 민감한 수치는 구간 문자열(`"25-40%"`, `"6-15"`)이나 불린으로 변환해서 보낸다. 원본 금액·수량은
   보내지 않는다.
4. 응답 구조는 `schema.py`의 Pydantic 모델로 정의하고, 프롬프트에는 스키마를 손으로 적지 않는다.
   `model_json_schema()`가 자동으로 삽입된다.
5. 프롬프트는 `prompts/` 아래 모듈 상수로 두고, 끝에
   `KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION`을 붙인다.
6. 안전 관련 정책(라우팅·개인정보)은 끌 수 없고, 최적화 정책(캐시·예산·에스컬레이션)은 설정으로
   켠다.
7. 캐시 키에는 payload·프롬프트·모델·스키마·날짜가 모두 들어간다. 프롬프트 조립 방식이 바뀌면
   `CACHE_SCHEMA_VERSION`을 올린다.
8. 외부 라이브러리 예외는 `LLMCallError` 계열로 변환해 밖으로 내보낸다.

## 알아둘 만한 개선 지점

- `LLMRequest`/`LLMResponse`가 정의만 되고 `LLMGateway`에서 쓰이지 않는다. 토큰 사용량·검증 상태
  기록이 아직 배선되지 않았다.
- `schema.py`의 등급 필드가 `str`이다. `types.py`의 enum을 쓰면 JSON Schema에 허용값이 실린다.
- `router.py`의 `future_primary`는 계획일 뿐 현재 동작에 영향이 없다. 로컬 전환 시점에 실제
  전환 로직이 필요하다.

## 다음 단계로 이어지는 질문

- `get_redis_connection()`은 어디에 정의되어 있고 워커 큐와 어떻게 공유되는가? (08단계)
- LLM을 호출하는 무거운 작업은 요청 중에 도는가, 워커에서 도는가? (08단계)
- `JobRun` 테이블에는 무엇이 기록되는가? (08단계)
