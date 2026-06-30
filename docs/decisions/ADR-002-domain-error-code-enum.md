# ADR-002: Domain Error Code Enum

## Status

Accepted

## Context

API 클라이언트는 분기 처리와 지역화된 표시 동작을 위해 안정적인 에러 키가 필요하다.
HTTP 상태 코드만으로는 넓은 프로토콜 분류만 기술할 뿐이고, 현재 응답 본문은 지속적인
machine-readable 코드 없이 사람용 메시지만 노출한다.

## Decision

도메인별 문자열 값을 갖는 공유 `ErrorCode(str, Enum)`을 채택하고, 공통 에러 envelope에
담아 반환한다:

- `data: null`
- `message`: 사용자 대면 메시지
- `error.code`: 안정적인 enum 값
- `error.fields`: 해당 시 검증 상세
- `meta: null`

`AppException`은 명시적 `error_code`를 요구하며, 프레임워크 검증/미처리 예외는 전역
핸들러를 통해 정규화된다.

## Alternatives

- HTTP 상태 코드만 사용.
- 각 raise 지점에서 임시 문자열 코드 사용.
- 사람이 읽는 에러 메시지만 반환.

## Consequences

프론트엔드 에러 처리는 한국어 표시 메시지를 파싱하지 않고 안정적인 코드로 분기할 수
있다. 백엔드 raise 지점은 다소 장황해지지만, `AppException`이 `error_code`를 요구하므로
누락된 매핑은 구현 중에 잡힌다.

새 도메인 에러가 추가될 때 코드 목록을 유지보수해야 한다.

## Follow-up

새 API 에러는 공통 envelope에 유지하고, 클라이언트에 보이는 새 에러 조건이 생기면 enum
값을 추가한다.

## Related Documents

- `docs/designs/027-error-handling.md`
- Issue #47
