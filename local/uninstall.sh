#!/usr/bin/env bash
# launchd 에이전트 해제. 상태 파일, 로그, .venv는 지우지 않는다.
set -euo pipefail

LABEL="com.xmfldksl.kmcc-note"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || echo "등록된 에이전트가 없습니다."
rm -f "$PLIST"
echo "해제 완료. 상태 파일($HOME/Library/Application Support/kmcc-note)과 로그, .venv는 남아 있습니다."
