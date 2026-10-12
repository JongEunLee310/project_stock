# 09. 파생과 판정 도메인 — signals, alert_engine

대상 파일: `app/domains/signals/*`, `app/domains/alert_engine/*`, `app/domains/alert_rules/types.py`,
`app/worker/jobs/alerts.py`

지금까지는 **데이터를 저장하고 보여주는** 코드였습니다. 이 단계는 **데이터를 보고 판단하는**
코드입니다. 성격이 다르므로 구조도 다릅니다.

| | signals | alert_engine |
| --- | --- | --- |
| 하는 일 | 종목의 현재 상태를 판정해 저장 | 사용자 규칙과 지표를 비교해 알림 발생 |
| 규칙의 출처 | 코드에 고정된 우선순위 | **DB에 저장된 사용자 규칙(JSON)** |
| 테이블 | `signals`, `asset_signal_snapshots` | `alert_rules`, `alert_events`, `alert_deliveries` |
| 진입점 | 분석 잡, 조회 API | `evaluate_alert_rules_job` (5분마다) |

`alert_engine`에는 `model.py`가 없습니다. **다른 도메인의 모델을 읽고 쓰는 순수 로직 계층**이기
때문입니다. 이 프로젝트에서 도메인 폴더가 반드시 테이블을 갖지는 않는다는 예입니다.

## signals — 판정 결과의 저장

### model.py — 근거를 함께 저장한다

```python
class Signal(Base):
    __tablename__ = "signals"

    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    thesis_id: Mapped[int | None] = ...        # 어떤 투자 논거와 연결되는가
    news_item_id: Mapped[int | None] = ...     # 어떤 뉴스가 계기였는가
    signal_type: Mapped[str] = mapped_column(String(20), index=True)
    score: Mapped[int]
    risk_level: Mapped[str | None]
    reason: Mapped[str] = mapped_column(Text)          # 왜 이 판정인가
    evidence: Mapped[str | None] = mapped_column(Text) # 근거
    key_points: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = ...
```

`reason`·`evidence`·`key_points`가 **판정 도메인의 핵심**입니다. "이 종목은 위험"이라는 결론만
저장하면 사용자가 신뢰할 수 없습니다. **왜 그렇게 판단했는지를 함께 저장**해야 검증 가능한
시스템이 됩니다.

`thesis_id`와 `news_item_id`가 nullable인 것도 같은 맥락 — 계기가 있으면 연결하고 없으면 비웁니다.

`Signal`이 `TimestampMixin`을 쓰지 않고 `created_at`만 직접 선언한 점이 눈에 띕니다. **시그널은
생성 후 수정되지 않는 이벤트**라는 뜻입니다. 상태가 바뀌면 UPDATE가 아니라 새 행을 만듭니다.

`expires_at`이 시그널의 수명을 관리합니다. "3일 전 급등 경고"가 영원히 붙어 있으면 안 되므로,
조회 시 만료된 것을 걸러냅니다.

### types.py — 우선순위를 코드로 고정

```python
class SignalType(str, Enum):
    WATCH = "WATCH"
    RISK_ALERT = "RISK_ALERT"
    THESIS_BROKEN = "THESIS_BROKEN"
    BUY_CANDIDATE = "BUY_CANDIDATE"
    SELL_REVIEW = "SELL_REVIEW"
    OVERHEATED = "OVERHEATED"

SIGNAL_TYPE_CATEGORY: dict[SignalType, SignalCategory] = {
    SignalType.WATCH: SignalCategory.WATCH,
    SignalType.RISK_ALERT: SignalCategory.RISK,
    SignalType.THESIS_BROKEN: SignalCategory.RISK,
    ...
}
```

**타입 6개를 카테고리 4개로 접습니다.** 화면에서는 카테고리 단위로 묶어 보여주고, 저장은 세분화된
타입으로 합니다. 표현 단위와 저장 단위를 분리한 형태입니다.

```python
WATCHLIST_STATUS_PRIORITY: tuple[SignalType, ...] = (
    SignalType.RISK_ALERT,      # 가장 급한 것
    SignalType.THESIS_BROKEN,
    SignalType.SELL_REVIEW,
    SignalType.OVERHEATED,
    SignalType.BUY_CANDIDATE,
    SignalType.WATCH,           # 가장 덜 급한 것
)

def resolve_watchlist_status(active_types: set[str]) -> str:
    for signal_type in WATCHLIST_STATUS_PRIORITY:
        if signal_type.value in active_types:
            return signal_type.value
    return WATCHLIST_STATUS_NORMAL
```

**한 종목에 여러 시그널이 동시에 살아 있을 때 무엇을 대표로 보여줄지**를 정하는 규칙입니다.
튜플 순서가 곧 우선순위이고, 앞에서부터 찾아 처음 걸리는 것을 씁니다.

이 함수가 04단계 `WatchlistService.list_items_expanded`에서 호출됩니다. 관심목록의 각 종목에
붙는 상태 배지가 여기서 결정됩니다.

**위험이 기회보다 앞에 있는 것**이 도메인 판단입니다. 위험 신호와 매수 후보가 동시에 뜨면 위험을
보여줍니다.

```python
def signal_priority_rank(signal_type: str | None) -> int | None:
    rank_by_type = {status_type.value: rank for rank, status_type in enumerate(WATCHLIST_STATUS_PRIORITY)}
    return rank_by_type.get(signal_type, len(rank_by_type))
```

같은 튜플에서 정렬용 숫자를 뽑습니다. 모르는 타입은 `len(rank_by_type)`(맨 뒤)으로 보내 **새
타입이 추가돼도 정렬이 깨지지 않게** 합니다.

```python
def signal_category_for_type(signal_type: str | None) -> SignalCategory | None:
    try:
        typed_signal = SignalType(signal_type)
    except ValueError:
        return None
```

**문자열 → enum 변환에 `try/except ValueError`가 필요합니다.** 03단계에서 본 대로 DB 컬럼이
`String`이므로, 오래된 행에 지금은 없는 값이 들어 있을 수 있습니다. `String` + 파이썬 enum 조합의
대가가 여기서 드러납니다.

### snapshot_model.py — 변화를 추적하기 위한 일별 기록

```python
class AssetSignalSnapshot(Base):
    __table_args__ = (
        UniqueConstraint("asset_id", "snapshot_date", name="uq_asset_signal_snapshots_asset_date"),
    )
    asset_id / snapshot_date / signal_id / signal_type / score / captured_at
```

**종목 × 날짜당 한 행**입니다. 08단계의 `snapshot_signal_states_job`(평일 11:30 UTC)이 매일
"오늘 이 종목의 대표 시그널은 무엇인가"를 찍어 둡니다.

`signals` 테이블만으로는 "어제는 안전이었는데 오늘 위험으로 바뀌었다"를 알기 어렵습니다. 시그널은
생겼다 만료되는 이벤트라 특정 시점의 상태를 재구성하려면 복잡한 쿼리가 필요합니다. **일별
스냅샷을 따로 만들어 변화 비교를 단순한 두 행 비교로 바꾼 것**입니다.

```python
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), nullable=True)
```

`ondelete="SET NULL"`이 이 프로젝트에서 드문 명시적 FK 동작입니다. 원본 시그널이 삭제돼도
**스냅샷은 남고 링크만 끊깁니다.** 과거 기록의 보존을 우선한 선택이며, `signal_type`과 `score`를
스냅샷에 복사해 두었기 때문에 링크가 끊겨도 정보가 남습니다. 정규화를 일부러 깬 것입니다.

### service.py — 04단계의 N+1이 여기서는 해결되어 있다

```python
        asset_ids = [signal.asset_id for signal in signals]
        assets = {asset.id: asset for asset in self.asset_repo.list_by_ids(asset_ids)}
        symbols = [asset.symbol for asset in assets.values()]
        quotes = {quote.symbol: quote for quote in get_market_provider().get_quote(symbols)} if symbols else {}
```

05단계에서 "도구는 있는데 안 쓴다"고 했던 `list_by_ids`를 **여기서는 제대로 씁니다.** 같은 조립
작업인데 04단계 `WatchlistService`는 루프 단건 조회, 여기는 배치 조회입니다. 같은 코드베이스
안에서 품질이 균일하지 않다는 것을 보여주는 좋은 비교 사례입니다.

## alert_engine — 사용자 규칙 엔진

### 규칙이 데이터다

```python
class AlertMetric(str, Enum):
    NEWS_RISK / PRICE_CHANGE_1D / SIGNAL_CHANGED / AI_JUDGMENT_CHANGED
    THEME_HEAT / POSITION_WEIGHT / EARNINGS_DATE / TOPIC_IMPACT_SCORE

class AlertOperator(str, Enum):
    EQ / GTE / LTE / CHANGED

class AlertTargetType(str, Enum):
    SYMBOL / WATCHLIST / PORTFOLIO / TOPIC / MARKET
```

**지표 8개 × 연산자 4개 × 대상 5종**의 조합으로 규칙을 만듭니다. 규칙은 `AlertRule.condition`
JSON 컬럼에 저장됩니다.

```json
{"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"}
{"all": [
  {"metric": "PRICE_CHANGE_1D", "operator": "LTE", "value": -5},
  {"metric": "NEWS_RISK", "operator": "GTE", "value": "MEDIUM"}
]}
```

**새 알림 조건을 추가할 때 코드 배포가 필요 없습니다.** 대신 조건 JSON을 해석하는 인터프리터가
필요하고, 그것이 `evaluator.py`입니다.

`AlertTemplateType`(`HOLDING_NEWS_RISK`, `EARNINGS_D3` 등)은 사용자가 JSON을 직접 쓰지 않아도
되도록 미리 만들어둔 **규칙 템플릿**입니다. 04단계의 `WatchlistAlertRuleService`가 이것을
관심목록에 적용합니다.

### 4개 컴포넌트의 역할 분담

```text
snapshot_provider.py (459줄)  규칙이 요구하는 지표의 현재값·이전값을 모아온다
evaluator.py         (195줄)  조건 JSON을 해석해 참/거짓 판정
dedup.py             (125줄)  같은 알림을 반복 발송하지 않게 거른다
service.py           (148줄)  위 셋을 조립해 사이클 실행
```

`snapshot_provider`가 가장 큰 이유는 지표 8종이 각각 다른 테이블에서 오기 때문입니다. 뉴스 위험은
`news_items`, 가격 변동은 `stock_price_bars`, 포지션 비중은 `positions`에서 옵니다.

```python
@dataclass(frozen=True)
class MetricSnapshot:
    values: dict[AlertMetric, MetricValue]
    previous_values: dict[AlertMetric, MetricValue]      # 변화 감지용
    evidence: dict[AlertMetric, list[dict[str, Any]]]    # 근거
    unsupported_metrics: frozenset[AlertMetric]          # 이 대상에 적용 불가
    asset_id: int | None
    unavailable_reasons: dict[AlertMetric, MetricUnavailableReason]
```

**"값이 없음"을 세 가지로 구분**하는 것이 이 타입의 핵심입니다.

| 구분 | 의미 | 처리 |
| --- | --- | --- |
| `unsupported_metrics` | 이 대상 타입에 애초에 적용 불가 (예: MARKET 대상에 POSITION_WEIGHT) | 규칙 전체를 건너뜀 |
| `unavailable` + `NO_TARGET` | 대상이 없음 (빈 관심목록) | 평가 건너뜀 |
| `unavailable` + `NO_DATA` | 대상은 있는데 데이터가 없음 | 평가 건너뜀 |

**데이터가 없을 때 조용히 "조건 불충족"으로 처리하지 않는 것**이 중요합니다. 그러면 "위험이
없어서 알림이 안 온 것"과 "데이터가 없어서 판단 못 한 것"이 구분되지 않습니다. 판정 시스템에서
가장 위험한 실패 모드를 타입으로 막았습니다.

### evaluator.py — 조건 인터프리터

```python
    def evaluate_rule(self, rule: AlertRule, snapshot: MetricSnapshot) -> AlertEvaluationResult:
        condition = rule.condition
        if set(condition) == {"all"}:
            evaluations = [self._evaluate_condition(member, snapshot) for member in condition["all"]]
            triggered_value = {"conditions": [item.triggered_value for item in evaluations]}
        else:
            evaluations = [self._evaluate_condition(condition, snapshot)]
            triggered_value = evaluations[0].triggered_value
        matched = all(item.matched for item in evaluations)
```

`set(condition) == {"all"}`로 **복합 조건인지 단일 조건인지 판별**합니다. 키가 정확히 `all` 하나일
때만 복합으로 봅니다. `"all"` 하나만 지원하므로 현재는 AND만 가능하고, OR(`"any"`)은 없습니다.

```python
    def _compare(self, metric, operator, current, threshold, *, previous, has_previous) -> bool:
        if operator == AlertOperator.CHANGED:
            return has_previous and current != previous
        if operator == AlertOperator.EQ:
            return current == threshold

        current_ordered = self._ordered_value(metric, current)
        threshold_ordered = self._ordered_value(metric, threshold)
        if current_ordered is not None and threshold_ordered is not None:
            left, right = float(current_ordered), float(threshold_ordered)
        elif self._is_number(current) and self._is_number(threshold):
            left, right = float(current), float(threshold)
        else:
            return False
        if operator == AlertOperator.GTE:
            return left >= right
        return left <= right
```

**순서 있는 문자열을 숫자로 바꿔 비교**하는 것이 핵심 기법입니다.

```python
_ORDERED_VALUES = {
    AlertMetric.NEWS_RISK: {"LOW": 0, "MEDIUM": 1, "HIGH": 2},
    AlertMetric.THEME_HEAT: {"COLD": 0, "NEUTRAL": 1, "OVERHEATED": 2},
}
```

`"뉴스 위험 >= MEDIUM"`이라는 조건을 문자열 비교로 처리할 수 없습니다(`"HIGH" >= "MEDIUM"`은
사전순으로 false). 등급을 정수로 매핑해 숫자 비교로 바꿉니다. **등급형 지표와 수치형 지표를 한
연산자 집합으로 다루는** 방법입니다.

비교 불가능한 조합(문자열인데 매핑에 없음)은 `return False`로 조용히 불일치 처리합니다.

```python
    def _is_number(self, value: object) -> TypeGuard[Real]:
        return isinstance(value, Real) and not isinstance(value, bool)
```

07단계 `escalation.py`와 **똑같은 bool 방어**입니다. `isinstance(True, Real)`이 참이므로 이 검사가
없으면 `True`가 `1.0`으로 비교됩니다. `TypeGuard`는 mypy에게 "이 함수가 True를 반환하면 인자는
`Real`이다"라고 알려주는 타입 힌트로, 이후 `float(current)` 호출에서 타입 오류가 나지 않게 합니다.

### 지문(fingerprint) — 같은 알림인지 판별하는 열쇠

```python
        fingerprint_payload = {"condition": condition, "triggered_value": triggered_value}
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
```

**조건 + 실제 발동값**의 해시입니다. 조건이 같아도 값이 다르면 다른 알림입니다 — "주가 -5% 하락"과
"주가 -12% 하락"은 같은 규칙이지만 다른 사건입니다.

`sort_keys=True` + `separators`는 05·06·07단계와 같은 해시 안정화입니다. **이 프로젝트에서 해시를
만들 때마다 반복되는 관용구**입니다.

### `is_transition` — 상태가 바뀐 순간

```python
            is_transition=has_previous and current != previous,
```

"위험이 HIGH다"와 "위험이 MEDIUM에서 HIGH로 바뀌었다"는 다릅니다. 전자는 조건이 유지되는 한 5분마다
참이지만, 후자는 바뀐 그 순간에만 참입니다. `ONCE_PER_TRANSITION` 정책이 이 값을 씁니다.

`has_previous`가 필요한 이유는 **이전 값 자체가 없는 첫 평가**를 전이로 오인하지 않기 위해서입니다.

## dedup.py — 알림 폭탄 방지

5분마다 도는 엔진에서 중복 억제가 없으면 같은 알림이 하루 288번 옵니다. 방어가 **네 겹**입니다.

```python
    def should_emit(self, rule, result, *, asset_id, now) -> bool:
        if not result.matched:
            return False
        if self._in_cooldown(rule, asset_id, now):                    # ① 쿨다운
            return False
        policy = AlertDeliveryPolicy(rule.delivery_policy)
        if policy == AlertDeliveryPolicy.ONCE_PER_TRANSITION and not result.is_transition:
            return False                                              # ② 전이일 때만
        if policy == AlertDeliveryPolicy.ONCE_PER_DAY and self._emitted_today(rule, asset_id, now):
            return False                                              # ③ 하루 한 번
        dedup_key = self.build_dedup_key(rule, result, asset_id=asset_id, now=now)
        return not self._dedup_key_exists(rule.user_id, dedup_key)    # ④ 같은 키 이미 존재
```

**규칙별 쿨다운(시간 기반) → 정책(의미 기반) → 지문(내용 기반)** 순서로 걸러집니다. 비싼 검사가
뒤로 가도록 배치되어 있습니다.

```python
    def build_dedup_key(self, rule, result, *, asset_id, now) -> str:
        fingerprint = result.event_fingerprint
        if rule.delivery_policy == AlertDeliveryPolicy.ONCE_PER_DAY.value:
            fingerprint = f"{fingerprint}:{self._as_utc(now).date().isoformat()}"
        digest = hashlib.sha256(fingerprint.encode()).hexdigest()
        target_id = rule.target_id if rule.target_id is not None else "-"
        asset_key = str(asset_id) if asset_id is not None else "-"
        return f"{rule.id}:{target_id}:{asset_key}:{digest}"
```

`ONCE_PER_DAY`일 때 **날짜를 지문에 섞습니다.** 어제와 오늘의 같은 상황이 다른 키가 되므로,
날짜가 바뀌면 다시 알림이 갑니다. 07단계 LLM 캐시 키에 날짜를 넣은 것과 같은 발상입니다.

`None`을 `"-"`로 치환하는 것은 키 구분자 충돌을 막기 위한 것입니다. `None`을 그냥 문자열로 넣으면
`"None"`이 되어 실제 값 `"None"`과 구분되지 않습니다.

## service.py — 사이클 조립

```python
        rules = list(self.db.scalars(
            select(AlertRule).where(AlertRule.enabled.is_(True)).order_by(AlertRule.id)).all())
        for rule in rules:
            snapshots = self.snapshot_provider.get_snapshots(rule, as_of=evaluated_at)
            if snapshots and snapshots[0].unsupported_metrics:
                counters["evaluated_count"] += 1
                counters["unsupported_count"] += 1
                continue
            for snapshot in snapshots:
                ...
```

규칙 하나가 **여러 스냅샷**을 낳습니다. 관심목록 대상 규칙이면 그 안의 종목 수만큼 나옵니다.

```python
            if emitted_for_rule:
                rule.last_triggered_at = evaluated_at
        self.db.flush()
```

**`commit()`이 아니라 `flush()`** 입니다. 03단계에서 본 "repository가 커밋한다" 규칙에서 벗어나
여기서는 **트랜잭션 제어를 호출부에 맡깁니다.** `evaluate_alert_rules_job`이 마지막에 `db.commit()`을
부르므로, 한 사이클의 모든 이벤트가 원자적으로 확정됩니다. 04단계에서 지적한 트랜잭션 경계
한계를 이 도메인에서는 다르게 해결한 것입니다.

### `begin_nested()` — 부분 롤백

```python
    def _create_event(self, rule, asset_id, result, dedup_key, triggered_at) -> bool:
        try:
            with self.db.begin_nested():
                event = AlertEvent(..., dedup_key=dedup_key, ...)
                self.db.add(event)
                self.db.flush()
                for channel in dict.fromkeys(rule.channels):
                    self.db.add(AlertDelivery(alert_event_id=event.id, channel=channel, ...))
                self.db.flush()
        except IntegrityError:
            return False
        return True
```

**`begin_nested()`는 SAVEPOINT를 만듭니다.** 이 블록 안에서 실패하면 SAVEPOINT까지만 롤백되고
바깥 트랜잭션은 살아남습니다. `dedup_key` 유니크 제약에 걸려도 **앞서 만든 다른 이벤트들이 함께
날아가지 않습니다.**

이것이 없으면 03단계에서 본 "PostgreSQL은 에러 후 트랜잭션 전체를 거부한다" 문제로 사이클 전체가
멈춥니다. 04단계 `add_item`처럼 각자 커밋하는 방식으로는 원자성을 얻을 수 없고, 여기서는
SAVEPOINT로 **원자성과 부분 실패 허용을 동시에** 달성했습니다. 이 코드베이스에서 트랜잭션을 가장
정교하게 다루는 지점입니다.

`IntegrityError`를 `False`로 변환하는 것은 dedup의 **다섯 번째 방어**입니다. `should_emit`이
확인한 뒤 INSERT 사이에 다른 프로세스가 같은 이벤트를 넣었다면 DB 제약이 잡습니다. 04단계
"service 사전 확인 + DB 최종 보장" 패턴의 반복입니다.

```python
                for channel in dict.fromkeys(rule.channels):
```

`set`이 아니라 `dict.fromkeys`입니다. 05단계 `_deduplicate`와 같은 이유 — **중복 제거 + 순서
유지**입니다.

```python
                            status=(AlertDeliveryStatus.SUCCESS.value if is_app
                                    else AlertDeliveryStatus.PENDING.value),
```

**채널별 전달 상태를 따로 기록**합니다. 앱 내 알림은 저장이 곧 전달이므로 즉시 `SUCCESS`,
이메일·Discord는 별도 발송이 필요하므로 `PENDING`입니다. 발송 실패 시 재시도할 수 있는 구조를
미리 만들어 둔 것입니다.

### 결과 집계

```python
@dataclass(frozen=True)
class AlertCycleSummary:
    evaluated_count / matched_count / emitted_count
    deduplicated_count / unsupported_count / unavailable_count

    def as_metadata(self) -> dict[str, int]:
        return {...}
```

05단계 `IngestionResult`와 같은 패턴이지만 **누적 방식이 다릅니다.** 여기서는 `counters` dict로
누적하다 마지막에 한 번 만듭니다. 05단계의 "매번 새 frozen 객체 생성"보다 실수 여지가 적습니다.

`as_metadata()`가 08단계의 `JobRun.metadata_`에 그대로 들어갑니다.

```python
        summary = AlertEngineService(db).run_cycle()
        job_run_service.succeed(job_run.id)
        job_run.metadata_ = summary.as_metadata()
        db.commit()
```

이 `db.commit()`이 사이클 전체(모든 `AlertEvent`, `AlertDelivery`, `last_triggered_at`, JobRun
메타데이터)를 한 번에 확정합니다.

## 전체 흐름 — 5분마다 도는 알림 사이클

```text
scheduler (cron */5) → Redis 큐 → worker: evaluate_alert_rules_job
  SessionLocal() / JobRun(running)
    ↓
  AlertEngineService.run_cycle()
    enabled=True인 AlertRule 전체 조회
    각 규칙마다:
      snapshot_provider.get_snapshots(rule)   지표 현재값·이전값·근거 수집
        └ unsupported면 규칙 건너뜀
      각 스냅샷마다:
        evaluator.evaluate_rule()             조건 JSON 해석 → matched, fingerprint, is_transition
          └ unavailable이면 건너뜀 (조건 불충족과 구분)
        dedup.should_emit()                   쿨다운 → 정책 → 지문 존재 확인
        _create_event()                       SAVEPOINT 안에서 AlertEvent + AlertDelivery
          └ IntegrityError면 중복으로 간주하고 계속
      발생했으면 rule.last_triggered_at 갱신
    db.flush()
    ↓
  JobRun(success) + metadata_ = 집계
  db.commit()      ← 사이클 전체를 원자적으로 확정
```

## 이 단계에서 확인한 프로젝트 규칙

1. 판정 결과는 결론뿐 아니라 `reason`·`evidence`를 함께 저장한다.
2. 여러 판정이 겹칠 때의 우선순위는 `types.py`의 튜플 순서로 고정한다. 위험이 기회보다 앞선다.
3. 변화 추적이 필요하면 일별 스냅샷 테이블을 따로 두고, 필요한 값은 복사해 링크가 끊겨도 남게
   한다.
4. **"조건 불충족"과 "데이터 없음"을 구분한다.** 판정 시스템에서 조용한 실패는 최악이다.
5. 사용자 규칙은 JSON 컬럼에 저장하고 인터프리터로 해석한다. 규칙 추가에 배포가 필요 없게 한다.
6. 등급형 문자열은 정수 매핑(`_ORDERED_VALUES`)으로 바꿔 수치 비교와 같은 연산자로 다룬다.
7. 반복 발송은 쿨다운·정책·내용 지문·DB 유니크 제약을 겹쳐 막는다.
8. 여러 테이블을 원자적으로 써야 하면 service가 `flush()`만 하고 커밋은 호출부(잡)가 한다.
   항목 단위 실패 격리는 `begin_nested()`(SAVEPOINT)로 처리한다.
9. 숫자 비교 전에는 `not isinstance(value, bool)`을 확인한다.

## 알아둘 만한 개선 지점

- 조건 JSON이 `all`(AND)만 지원한다. `any`(OR)나 중첩 조건은 없다.
- `AlertRule.condition`은 검증 없이 저장되므로 잘못된 지표명이 들어가면 평가 시점에 `ValueError`가
  난다. 저장 시 Pydantic 검증이 있으면 더 안전하다.
- `signal_category_for_type`의 `try/except ValueError`는 `String` 컬럼 + 파이썬 enum 조합의 비용이다.
- 04단계 `WatchlistService`가 `list_by_ids`를 쓰지 않는 것과 달리 `SignalService`는 제대로 쓴다.
  같은 패턴이 도메인마다 다르게 구현되어 있다.

## 다음 단계로 이어지는 질문

- `news_insights`의 Document → Event → Topic 3층 구조는 무엇인가? (10단계)
- `decision_logs`가 ADR로 재설계된 이유와 6개 테이블 구조는? (10단계)
- 1,000줄 넘는 repository는 어떻게 구성되어 있는가? (10단계)
