"""GitHub App installation access token 발급기.

봇(GitHub App) 명의로 코멘트를 게시하기 위한 1시간짜리 installation token을 stdout에
출력한다. 비밀은 코드에 두지 않고 환경변수로 받는다.

필요 환경변수:
- CLAUDE_BOT_APP_ID            : GitHub App의 App ID (숫자)
- CLAUDE_BOT_PRIVATE_KEY_PATH  : App private key(.pem) 경로
                                 (기본: ~/.config/claude-bot/private-key.pem)
- CLAUDE_BOT_REPO              : owner/repo (기본: JongEunLee310/project_stock)

실행(프로젝트 의존성 오염 없이):
    uv run --with pyjwt --with cryptography python scripts/claude-bot-token.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import jwt

API = "https://api.github.com"


def _fail(message: str) -> "None":
    print(f"claude-bot-token: {message}", file=sys.stderr)
    raise SystemExit(1)


def _api_get(path: str, token: str) -> dict:
    return _api(path, token, method="GET")


def _api(path: str, token: str, method: str) -> dict:
    request = urllib.request.Request(f"{API}{path}", method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        _fail(f"{method} {path} -> {exc.code} {exc.read().decode(errors='replace')}")
        raise  # unreachable


def main() -> None:
    app_id = os.environ.get("CLAUDE_BOT_APP_ID")
    if not app_id:
        _fail("CLAUDE_BOT_APP_ID 환경변수가 없습니다.")

    key_path = Path(
        os.environ.get(
            "CLAUDE_BOT_PRIVATE_KEY_PATH",
            str(Path.home() / ".config" / "claude-bot" / "private-key.pem"),
        )
    ).expanduser()
    if not key_path.is_file():
        _fail(f"private key를 찾을 수 없습니다: {key_path}")

    repo = os.environ.get("CLAUDE_BOT_REPO", "JongEunLee310/project_stock")
    private_key = key_path.read_text()

    now = int(time.time())
    app_jwt = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": app_id},
        private_key,
        algorithm="RS256",
    )

    installation = _api_get(f"/repos/{repo}/installation", app_jwt)
    installation_id = installation["id"]

    token_response = _api(
        f"/app/installations/{installation_id}/access_tokens",
        app_jwt,
        method="POST",
    )
    print(token_response["token"])


if __name__ == "__main__":
    main()
