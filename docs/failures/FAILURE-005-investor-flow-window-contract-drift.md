# FAILURE-005: 투자자 동향 window 계약 불일치

## Status

Accepted

## Background

뉴스 인사이트 시드는 투자자 동향 행의 집계 구간 라벨을 `window="5d"`로 저장했지만, 화면은
`window=7d`로 투자자 동향 API를 조회했다.

## Failed Approach

리포지토리가 조회 `window`를 기간이 아니라 저장 라벨의 완전 일치 조건으로 사용했다. 계약
테스트도 시드와 같은 `window=5d`만 요청해 이 결합을 그대로 통과시켰다.

## Failure Cause

요청의 조회 기간과 저장 행의 집계 기준이라는 서로 다른 개념을 하나의 문자열 일치 조건으로
취급했다. 시드·기존 테스트의 값은 서로 같았지만 실제 화면 파라미터와 달라, 계약·모델·화면을
연결한 검증이 없었다.

## Impact

`window=7d` 요청은 항상 행 0건이 되었고 패널은 빈 상태만 표시했다. 서비스가 이를 정상적인
`availability.available = false` 응답으로 바꿔 HTTP 200을 반환했기 때문에 오류로 드러나지
않았다.

## Replacement Decision

서비스가 고정 가능한 기준 시각과 파싱한 기간을 리포지토리에 전달하고, 리포지토리는
`as_of >= 기준 시각 - window`로 조회한다. 저장 `window`는 실제 집계 기준 라벨로 유지하며
응답의 `aggregation_windows`로 노출한다.

## Retry Conditions

저장 라벨 완전 일치 방식으로 돌아가지 않는다. 조회 기간과 집계 기준을 별도 계약으로 유지한다.

## Related Documents

- Issue #390
- `docs/designs/307-news-intelligence-phase2.md`
- `tests/test_news_insights.py`의 실제 화면 파라미터(`market=KR`, `window=7d`) 회귀 테스트
