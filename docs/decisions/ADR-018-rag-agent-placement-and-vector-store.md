# ADR-018: RAG Agent Placement — BE 내부 모듈 + pgvector, 분리·전환 트리거

## Status

Proposed

## Context

벡터 검색, RAG, Obsidian을 사용하는 AI agent를 도입한다. 첫 적용 기능은 **종목 리서치
Q&A**로 정했다. 리서치 상세에서 받은 질문에 수집된 근거를 인용해 답하는 기능이다.
설계 과정에서 확인된 전제는 다음과 같다.

1. **코퍼스는 BE DB에 있다.** 1차 근거는 `source_documents`(정본 `raw_news_events`)이고,
   종목 매핑은 `news_items.asset_id`가 가지고 있다. 2단계 후보인 판단 기록도 BE DB에 있다.
2. **Obsidian vault는 아직 비어 있다.** 그래서 1차에서 vault는 근거 소스가 아니라 agent
   결과를 내보내는 출력 대상으로 쓴다. 사용자 노트를 다시 읽어 코퍼스에 넣는 일은
   2단계에서 다룬다.
3. **LLM 기반 계층이 이미 있다.** `LLMGateway`, `PrivacyGate`(ADR-009), router, budget,
   cache, 구조화 출력이 BE에 있다.
4. **repo 전체가 sync다.** ADR-007에서 async를 도입하지 않기로 결정했다.
5. **규모가 작다.** 사용자는 1명이고 뉴스 원천은 수천 건 수준이다(`raw_news_events` 약
   2,622건, 출처: `docs/designs/397-collection-source-documents.md`).

이 ADR은 두 가지를 결정한다. agent 코드를 어디에 둘지와 벡터 저장소로 무엇을 쓸지다.
아울러 그 결정을 **언제 다시 열어야 하는지**를 트리거로 명시한다. 트리거를 미리 적어
두지 않으면 분리나 전환이 감각에 따라 이뤄지고, 반대로 필요한 시점을 놓치기 쉽다.

## Decision

### 1. 배치 — BE 프로젝트 내부 모듈로 시작한다

agent는 별도 프로젝트로 나누지 않고 BE 안에 둔다. 코드는 다음 위치에 모은다.

- `app/domains/rag/` — 청크 모델, 인덱싱, 검색·생성 서비스, API
- `app/adapters/vector/` — `VectorStore` ABC와 구현체
- `app/adapters/embedding/` — `Embedder` ABC와 구현체(OpenAI, Mock)

### 2. 벡터 저장소 — pgvector를 쓴다

기존 Postgres에 `pgvector` 확장을 추가한다. compose 이미지는 `postgres:16-alpine`에서
`pgvector/pgvector:pg16`으로 바꾼다. 저장소 접근은 `VectorStore` ABC 뒤에 두고, 구현체는
`adapters/factory.py`의 provider 선택 패턴에 따라 `VECTOR_STORE_PROVIDER` 설정으로 고른다.
1차 구현체는 `PgVectorStore` 하나다.

### 3. 분리 가능성을 유지하는 경계 규칙

나중에 프로젝트를 분리하거나 전용 vector DB로 옮길 때 비용이 작도록 처음부터 다음 규칙을
지킨다.

- **R1.** 다른 도메인은 `app/domains/rag/` 내부를 import하지 않는다. rag의 외부 노출은
  API와 service 공개 함수뿐이다.
- **R2.** rag가 다른 도메인 데이터를 읽을 때는 그 도메인의 service나 repository 공개
  함수를 거친다. 다른 도메인 테이블에 쓰기는 하지 않는다.
- **R3.** 벡터 저장소에는 정본을 두지 않는다. 원본은 각 도메인 테이블에 있고, 청크와
  벡터는 언제든 원본에서 다시 만들 수 있어야 한다.
- **R4.** `VectorStore.search`의 필터는 저장소 중립적인 형태로 정의한다. 예를 들어
  `asset_id`, `source_type`, `published_after`처럼 값으로 표현하고, SQL 조인이나 쿼리
  객체를 시그니처에 드러내지 않는다.
- **R5.** LLM 호출은 기존 `LLMGateway`를 거친다. rag 전용 LLM 클라이언트를 따로 만들지
  않는다.

### 4. 프로젝트 분리 트리거

아래 조건 중 하나라도 충족되면 **분리 검토 ADR을 새로 작성한다.** 트리거 충족이 곧 자동
분리를 뜻하지는 않는다. 검토 결과 BE 내부 유지로 결론이 날 수도 있다. 수치 기준은 현재
측정값이 없어 모두 가정이며, 실제 운영 수치가 쌓이면 이 ADR을 개정한다.

| ID | 트리거 | 판단 기준 |
|---|---|---|
| T1 | 실행 모델 충돌 | 도구 호출형 다회 루프, 토큰 스트리밍, 요청당 장시간 실행(가정: 30초 초과)이 필요해져 ADR-007의 sync 유지 결정과 충돌한다 |
| T2 | 무거운 의존성 | agent 프레임워크(LangGraph 등)나 로컬 모델 런타임(torch 등)을 도입해야 하고, 그 결과 BE 이미지 크기(가정: 500MB 이상 증가)나 CI 시간(가정: 50% 이상 증가)이 크게 늘어난다 |
| T3 | BE 외 소비처 | Obsidian 플러그인, CLI, 다른 서비스처럼 BE API를 거치지 않고 agent를 직접 호출하려는 소비처가 생긴다 |
| T4 | 실행 위치 제약 | vault 읽기·쓰기를 배포 환경에서도 해야 하거나, 로컬에서만 동작하는 agent 기능이 주요 기능이 된다 |
| T5 | 리소스·배포 주기 | GPU가 필요해지거나, agent 변경 때문에 BE 릴리스가 막히는 일이 반복된다(가정: 한 분기에 2회 이상) |

### 5. 전용 vector DB 전환 트리거

아래 조건 중 하나라도 충족되면 전용 vector DB(Qdrant 등) 전환을 검토한다. 수치 기준은
모두 가정이다.

| ID | 트리거 | 판단 기준 |
|---|---|---|
| V1 | 규모·지연 | 청크 수가 100만 건 이상이 되거나(가정), 검색 p95 지연이 500ms를 넘는다(가정) |
| V2 | 검색 기능 | 검색 품질 평가에서 하이브리드 검색(키워드+벡터)이나 재랭킹이 필요하다고 확인되고, Postgres 전문 검색 조합으로는 충족하기 어렵다 |
| V3 | 프로젝트 분리 동반 | T1~T5로 프로젝트를 분리하면 같은 DB에서 조인한다는 pgvector의 장점이 사라지므로 저장소 선택을 함께 재평가한다 |
| V4 | 학습 목적 실험 | 전용 vector DB를 경험하려는 목적의 전환 시도를 허용한다. 다만 같은 질문 세트로 두 구현체의 검색 품질과 지연을 비교하고, 결과를 `docs/experiments/`에 기록한다 |

전환할 때는 `VectorStore`의 새 구현체를 추가하고, 원본에서 다시 임베딩해 적재한 다음
`VECTOR_STORE_PROVIDER`를 바꾼다. R3 덕분에 데이터 이관이 따로 필요하지 않다.

## Alternatives

- **처음부터 별도 프로젝트로 시작.** 실행 모델과 의존성을 자유롭게 고를 수 있다. 하지만
  코퍼스를 읽으려면 BE API 계약을 새로 만들거나 DB에 직접 접속해야 한다. `LLMGateway`와
  `PrivacyGate`를 다시 만들거나 공유 패키지로 떼어 내야 하고, CI·하네스·리뷰 거버넌스를
  맞출 repo도 하나 늘어난다. 현재는 T1~T5 중 충족된 조건이 없어 기각한다.
- **처음부터 전용 vector DB(Qdrant/Chroma).** 하이브리드 검색과 운영 도구가 좋다. 하지만
  원본과 벡터를 이중으로 저장하게 되어 동기화 규칙이 필요하고, 종목·기간 필터용
  메타데이터도 복제해야 한다. 지금 규모에서는 성능 이점이 드러나지 않아 기각한다. 다만
  V4로 실험 경로는 열어 둔다.
- **FAISS 같은 인메모리 인덱스.** 영속성과 필터를 직접 구현해야 하고 프로세스 재시작마다
  다시 적재해야 한다. 기각한다.

## Consequences

- 인프라가 늘지 않는다. 기존 Alembic, 백업, CI에 벡터 데이터가 그대로 포함된다.
- 종목·기간 필터를 SQL 조인으로 처리할 수 있고, 원본을 삭제할 때 청크도 같은 트랜잭션에서
  정리할 수 있다.
- Postgres 이미지를 교체해야 한다. 로컬과 배포 compose 모두 바꿔야 하고, 기존 데이터
  볼륨과 호환되는지 확인해야 한다.
- `VectorStore` ABC는 구현체가 하나뿐인 추상화다. 이 ADR의 V1~V4 전환 경로를 위해 의도적으로
  둔다. 기존 `LLMClient` 패턴과 같은 수준이며, 그 이상의 추상화는 추가하지 않는다.
- R1~R5를 어기는 코드가 들어오면 분리 비용이 커진다. 로컬 리뷰에서 경계 위반 여부를
  확인 항목으로 본다.
- Obsidian 쓰기는 BE 컨테이너에 vault를 볼륨으로 마운트해야 하므로 1차에서는 로컬 compose
  전용 기능이다. 이 제약이 커지면 T4에 해당한다.

## Follow-up

- 종목 리서치 Q&A 설계 문서를 `docs/designs/`에 작성한다(청크 모델, 인덱싱 job, 검색·생성
  흐름, API, Obsidian 출력, 테스트).
- 임베딩 데이터 경계를 설계에서 다룬다. 1차 코퍼스는 공개 데이터인 `NEWS`로 한정하고,
  판단 기록 같은 개인 데이터의 임베딩은 ADR-009 CloudSafe 판정과 함께 2단계에서 결정한다.
- 이슈를 단계별로 분해해 등록한다(BE 1차, FE 질문 패널, 2단계 vault 읽기·판단 기록).
- 운영 수치(청크 수, 검색 지연, 이미지 크기, CI 시간)가 쌓이면 §4·§5의 가정 수치를 개정한다.

## Related Documents

- ADR-007 — LLM provider 추상화, sync 유지 결정
- ADR-009 — Cloud 데이터 경계(CloudSafe projection)
- ADR-003 — 스케줄러 방식(인덱싱 job 배치 근거)
- `docs/designs/397-collection-source-documents.md` — 1차 코퍼스 정본
