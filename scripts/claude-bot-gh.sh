#!/usr/bin/env bash
# 봇(GitHub App) 명의로 gh 명령을 한 번 실행한다.
# 커밋·push는 건드리지 않는다 — 이 래퍼를 통한 gh API 호출(코멘트·PR 등)만 봇 명의가 된다.
#
# 사용:
#   scripts/claude-bot-gh.sh pr comment 149 --body "..."
#   scripts/claude-bot-gh.sh api repos/OWNER/REPO/pulls/149/comments -f body=... -F in_reply_to=ID
#
# 선행: CLAUDE_BOT_APP_ID 환경변수 + private key(.pem) 준비 (scripts/claude-bot-token.py 참고)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 현재 repo를 자동 감지해 BE/FE에서 동일 스크립트가 동작하게 한다(설치된 App의 해당
# repo installation을 찾기 위함). 이미 지정돼 있으면 존중한다.
export CLAUDE_BOT_REPO="${CLAUDE_BOT_REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"

TOKEN="$(uv run --quiet --with pyjwt --with cryptography python "${ROOT}/scripts/claude-bot-token.py")"

GH_TOKEN="${TOKEN}" gh "$@"
