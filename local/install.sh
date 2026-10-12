#!/usr/bin/env bash
# launchd 에이전트 등록. 사용자 확인 후 실행한다.
#   1) .venv가 없으면 workflow와 같은 Python 3.12로 만들고 의존성 설치
#   2) 상태 파일을 ~/Library/Application Support/kmcc-note/ 로 한 번 복사 (이미 있으면 유지)
#   3) plist 템플릿을 치환해 ~/Library/LaunchAgents/ 에 복사하고 bootstrap
# 환경변수: PYTHON_BIN (Python 3.12 실행 파일 경로를 직접 지정할 때)
set -euo pipefail

LABEL="com.xmfldksl.kmcc-note"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_DIR/local/$LABEL.plist.template"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/kmcc-note"
STATE_DIR="$HOME/Library/Application Support/kmcc-note"
STATE_FILE="$STATE_DIR/seen_posts.txt"
VENV_DIR="$REPO_DIR/.venv"
DOMAIN="gui/$(id -u)"
REQUIRED_PY="3.12"   # .github/workflows/scraper.yml 의 python-version

if [[ ! -f "$REPO_DIR/.env.local" ]]; then
  echo ".env.local이 없습니다. .env.local.example을 복사해 값을 채운 뒤 다시 실행하십시오." >&2
  exit 1
fi

# --- Python 3.12 찾기 (설치하지 않는다) ---
find_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then echo "$PYTHON_BIN"; return; fi
  local c
  for c in "python$REQUIRED_PY" \
           "/opt/homebrew/opt/python@$REQUIRED_PY/bin/python$REQUIRED_PY" \
           "/usr/local/opt/python@$REQUIRED_PY/bin/python$REQUIRED_PY" \
           "/Library/Frameworks/Python.framework/Versions/$REQUIRED_PY/bin/python$REQUIRED_PY" \
           "$HOME/.pyenv/versions/$REQUIRED_PY"*/bin/python; do
    if command -v "$c" >/dev/null 2>&1; then command -v "$c"; return; fi
  done
  if command -v uv >/dev/null 2>&1; then
    uv python find "$REQUIRED_PY" 2>/dev/null && return
  fi
  return 1
}

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  PY_BIN="$(find_python || true)"
  if [[ -z "$PY_BIN" ]]; then
    echo "Python $REQUIRED_PY 을 찾지 못했습니다. 설치 후 다시 실행하십시오. 예: brew install python@$REQUIRED_PY" >&2
    echo "다른 경로에 있으면 PYTHON_BIN=/path/to/python$REQUIRED_PY local/install.sh" >&2
    exit 2
  fi
  if ! "$PY_BIN" -c "import sys; sys.exit(0 if sys.version_info[:2] == tuple(map(int, '$REQUIRED_PY'.split('.'))) else 1)"; then
    echo "$PY_BIN 은 Python $REQUIRED_PY 이 아닙니다: $("$PY_BIN" --version)" >&2
    exit 2
  fi
  echo "가상환경 생성: $VENV_DIR ($("$PY_BIN" --version))"
  "$PY_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install -q --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -q -r "$REPO_DIR/requirements.txt"
  touch "$VENV_DIR/.requirements.stamp"
else
  echo "가상환경 유지: $VENV_DIR ($("$VENV_DIR/bin/python" --version))"
fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR" "$STATE_DIR"

# --- 상태 파일 이어받기: 없을 때만 저장소의 seen_posts.txt를 한 번 복사 ---
if [[ ! -f "$STATE_FILE" ]]; then
  cp "$REPO_DIR/seen_posts.txt" "$STATE_FILE"
  echo "상태 파일 복사: seen_posts.txt -> $STATE_FILE"
else
  echo "상태 파일 유지: $STATE_FILE"
fi

sed -e "s|__REPO_DIR__|$REPO_DIR|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE" > "$PLIST"
plutil -lint "$PLIST"

# 이미 등록돼 있으면 해제 후 재등록
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl enable "$DOMAIN/$LABEL"

echo "등록 완료: $PLIST (월-금 10:30, 17:00)"
echo "확인: launchctl print $DOMAIN/$LABEL"
echo "로그: $LOG_DIR/YYYY-MM-DD.log"
