# Codex Tasks Index

Codex 핸드오프 task를 마일스톤별로 묶은 인덱스다. task 번호는 핸드오프 순서를
인코딩하며, 파일을 이동하지 않고 이 인덱스로만 버전 묶음을 제공한다. 새 task를
추가하면 다음 번호를 부여하고 아래 해당 마일스톤 목록에 한 줄을 추가한다.

번호 경계: v0.1은 `005`–`023`, v0.2는 `026`–`045`. task 번호는 design 번호와
1:1로 맞지 않는다(예: `task-008-news-db-domains`는 design `008`·`009` 두 개에 대응).
설계 인덱스는 [docs/designs/README.md](../../docs/designs/README.md)를 참고한다.

## v0.1 (005–023)

- [005 Asset Domain](task-005-asset-domain.md)
- [006 Watchlist Domain](task-006-watchlist-domain.md)
- [007 Investment Thesis Domain](task-007-investment-thesis-domain.md)
- [008 News DB Domains](task-008-news-db-domains.md)
- [009 News Adapter](task-009-news-adapter.md)
- [010 Worker Background Job](task-010-worker-background-job.md)
- [011 LLM Adapter](task-011-llm-adapter.md)
- [012 News AI Summary](task-012-news-ai-summary.md)
- [013 Thesis Conflict Analysis](task-013-thesis-conflict-analysis.md)
- [014 Research Report Domain](task-014-research-report-domain.md)
- [015 Signal Domain](task-015-signal-domain.md)
- [016 Rule Engine](task-016-rule-engine.md)
- [017 Alert Domain](task-017-alert-domain.md)
- [018 Watchlist Analysis Flow](task-018-watchlist-analysis-flow.md)
- [019 Portfolio Domain](task-019-portfolio-domain.md)
- [020 Portfolio Concentration](task-020-portfolio-concentration.md)
- [021 API and Integration Tests](task-021-api-and-integration-tests.md)
- [022 Worker Job Tests](task-022-worker-job-tests.md)
- [023 Project README](task-023-project-readme.md)

## v0.2 (026–045)

- [026 Common Response Format](task-026-common-response-format.md)
- [027 Error Handling](task-027-error-handling.md)
- [028 Frontend API Spec](task-028-frontend-api-spec.md)
- [029 Mock Data Provider](task-029-mock-data-provider.md)
- [030 Watchlist API Improvement](task-030-watchlist-api-improvement.md)
- [031 Asset Basic Info API](task-031-asset-basic-info-api.md)
- [032 Research Summary API](task-032-research-summary-api.md)
- [033 Decision Checklist API](task-033-decision-checklist-api.md)
- [034 Portfolio Summary API](task-034-portfolio-summary-api.md)
- [035 Alert Candidate API](task-035-alert-candidate-api.md)
- [036 List Query Conventions](task-036-list-query-conventions.md)
- [037 CORS Config](task-037-cors-config.md)
- [038 Config Structure](task-038-config-structure.md)
- [039 DB Migration Structure](task-039-db-migration-structure.md)
- [040 Major API Tests](task-040-major-api-tests.md)
- [041 API Contract Snapshot Tests](task-041-api-contract-snapshot-tests.md)
- [042 Logging Structure](task-042-logging-structure.md)
- [043 Health Check Improvement](task-043-health-check-improvement.md)
- [044 Scheduler Skeleton](task-044-scheduler-skeleton.md)
- [045 Backend v0.2 Integration Docs](task-045-backend-v0.2-docs.md)
