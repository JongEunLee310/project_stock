# Glossary

## Harness Engineering

A repeatable engineering system that scopes, verifies, reviews, and documents AI-assisted work.

## Claude Code

The orchestrator and reviewer responsible for planning, handoff, local PR review, and documentation assessment.

## Codex

The implementation agent responsible for code changes, tests, local verification, CI fixes, and review responses.

## Handoff

A structured task from Claude Code to Codex that defines scope, constraints, protected files, and verification.

## ADR

Architecture Decision Record. A durable record of a significant decision and its consequences.

## Failure Record

A durable record of a failed approach, its cause, impact, and retry conditions.

## Knowledge Base

Project documentation for workflow, glossary, domain knowledge, and reusable lessons.

## Feedback Loop

The cycle of issue, plan, implementation, PR, CI feedback, fix, local review, and human merge.

## Garbage Collection

The process of keeping docs and AI workflow artifacts current by keeping, updating, merging, archiving, or deleting them.

## Protected Files

Files that require explicit permission before modification.

## Documentation Drift

The gap between how the project actually works and what the documentation says.

## Product Domain Terms

투자 리서치/감시 제품 도메인 용어. 비즈니스 규칙과 상세는
`domain-knowledge.md`를 기준으로 한다.

### Investment Thesis

종목에 대한 투자 가설. 요약, 리스크 요인, 무효화 조건을 담는다.

### Signal

종목 변화에 대한 투자 시그널. 유형, 점수, 위험 수준, 만료 시각을 가진다.

### Alert

시그널에 기반해 사용자에게 전달된 알림. 읽음/숨김 처리 대상.

### Alert Candidate

발송 전 알림 후보. 사람이 검토해 읽음/확정한다. Alert와 별개 도메인이다.

### Concentration

포트폴리오 집중도. 시세 기반 비중이 `concentration_threshold`를 초과하면 과다 비중으로 본다.

### Buy Checklist

매수 전 점검 항목 묶음. 필수 키 전부 체크와 memo 입력이 있을 때 완료로 판정한다.

### Provider

market/news/disclosure/portfolio 외부 연동 어댑터. `mock` 또는 `real` 모드.
