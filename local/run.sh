#!/usr/bin/env bash
# kmcc-note 로컬 실행기 (launchd 또는 수동 실행용)
# GitHub Actions workflow(.github/workflows/scraper.yml)의 단계를 같은 순서로 수행한다.
#   1) 의존성 설치(requirements.txt가 바뀌었을 때만)  2) python -m src.main
# "발송 기록 커밋" 단계는 수행하지 않는다. 상태 파일(seen_posts.txt)은 저장소 밖(SEEN_FILE)에 두고
# 저장소의 seen_posts.txt는 읽지도 쓰지도 않는다.
#
# 사용법: local/run.sh [KEY=VALUE ...]
#   예: local/run.sh TEST_BOARDS=의사일정 SKIP_MAIL=1
#   KEY=VALUE 인자는 .env.local을 읽은 뒤에 적용되어 그 실행에만 쓰인다 (BACKFILL_FROM, FORCE_REPROCESS 등).
# 환경변수 재정의(테스트용): ENV_FILE, LOG_DIR, VENV_DIR, SEEN_FILE
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_DIR/.env.local}"
LOG_DIR="${LOG_DIR:-$HOME/Library/Logs/kmcc-note}"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv}"
LOCAL_STATE_DEFAULT="$HOME/Library/Application Support/kmcc-note/seen_posts.txt"
LOCK_DIR="${TMPDIR:-/tmp}/kmcc-note.lock"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"
exec >>"$LOG_FILE" 2>&1

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"; }

# 중복 실행 방지. 비정상 종료로 남은 lock은 수동 삭제 (rmdir "$LOCK_DIR").
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "이전 실행이 진행 중이어 건너뜁니다 (lock: $LOCK_DIR)"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$REPO_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

if [[ ! -f "$ENV_FILE" ]]; then
  log "환경 파일이 없습니다: $ENV_FILE (.env.local.example 참고)"
  exit 78
fi

# 비밀값은 환경변수로만 노출하고 로그에는 찍지 않는다. (set -x 사용 금지)
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# 이번 실행에만 적용할 KEY=VALUE 인자 (로그에는 키만 남긴다)
override_keys=()
for arg in "$@"; do
  if [[ "$arg" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
    export "$arg"
    override_keys+=("${arg%%=*}")
  else
    log "잘못된 인자(KEY=VALUE 형식이어야 함): $arg"
    exit 64
  fi
done

export SEEN_FILE="${SEEN_FILE:-$LOCAL_STATE_DEFAULT}"
PY="$VENV_DIR/bin/python"

if [[ ! -x "$PY" ]]; then
  log "가상환경이 없습니다: $VENV_DIR (local/install.sh를 먼저 실행)"
  exit 70
fi

# 상태 파일이 없으면 최근 7일치가 전부 신규로 발송되므로 멈춘다 (install.sh가 seen_posts.txt를 복사한다).
if [[ ! -f "$SEEN_FILE" ]]; then
  log "상태 파일이 없습니다: $SEEN_FILE (local/install.sh가 seen_posts.txt를 복사합니다)"
  exit 66
fi

log "시작 python=$PY ($("$PY" --version 2>&1)) SEEN_FILE=$SEEN_FILE overrides=[${override_keys[*]:-}]"

status=0
{
  # 1) 의존성 설치: requirements.txt가 마지막 설치 이후 바뀌었을 때만
  STAMP="$VENV_DIR/.requirements.stamp"
  if [[ ! -f "$STAMP" || "$REPO_DIR/requirements.txt" -nt "$STAMP" ]]; then
    log "pip install -r requirements.txt"
    "$PY" -m pip install -q -r "$REPO_DIR/requirements.txt"
    touch "$STAMP"
  fi

  # 2) 모니터링 실행. 코드가 datetime.now()+9h로 KST를 계산하므로(UTC runner 가정) TZ=UTC로 맞춘다.
  log "python -m src.main"
  TZ=UTC "$PY" -m src.main
} || status=$?

log "종료 코드=$status"
exit "$status"
