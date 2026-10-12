# 로컬 launchd 실행

GitHub Actions가 계정 단위로 비활성화된 동안(2026-09-24~) 맥의 launchd가 예약 실행을 대신한다.
평일(월-금) KST 10:30, 17:00에 `local/run.sh`를 실행하며, 상태 파일은 저장소 밖에 둔다.

## 준비
- Python 3.12 (workflow와 동일). 없으면 `brew install python@3.12` 등으로 직접 설치한다. install.sh는 설치하지 않는다.
- `cp .env.local.example .env.local` 후 값을 채운다. (.env.local은 git에서 무시됨)

## 설치
1. `local/install.sh` 실행. `.venv` 생성과 의존성 설치, `seen_posts.txt`를 `~/Library/Application Support/kmcc-note/seen_posts.txt`로 한 번 복사(이미 있으면 유지), 에이전트 등록을 한다.
2. 확인: `launchctl print gui/$(id -u)/com.xmfldksl.kmcc-note`

## 해제
`local/uninstall.sh` (상태 파일, 로그, .venv는 유지)

## 로그
- `~/Library/Logs/kmcc-note/YYYY-MM-DD.log`: 실행 단계와 종료 코드
- `~/Library/Logs/kmcc-note/launchd.log`: run.sh 시작 전 오류

## 수동 실행
```bash
local/run.sh                                   # 정기 실행과 동일
local/run.sh TEST_BOARDS=의사일정 SKIP_MAIL=1   # 이번 실행에만 적용할 옵션
local/run.sh BACKFILL_FROM=2026-09-24          # 중단 기간 소급 수집 (실제 발송됨)
```
출력은 터미널이 아니라 위 로그 파일에 기록된다. 실제 수집·메일·노션 전송이 일어나므로 주의한다.

## 주의
- 맥이 잠자기 상태면 예약 시각에 실행되지 않고, 깨어난 직후 밀린 예약이 1회 실행된다. 전원이 꺼져 있으면 건너뛴다(코드의 LOOKBACK_DAYS=7로 다음 실행이 복구 수집). 전원 연결 시 잠자기 방지(시스템 설정 > 배터리 > 옵션)는 사용자가 직접 설정한다.
- 상태 파일은 저장소에 commit하지 않는다. 저장소의 `seen_posts.txt`는 Actions 시절 기록으로 그대로 둔다.
- 비정상 종료로 `$TMPDIR/kmcc-note.lock`이 남으면 `rmdir`로 지운다.

## Actions 복구 시 되돌리기
1. `local/uninstall.sh`로 에이전트 해제 (이중 실행 방지)
2. 로컬 상태를 이어받으려면 `~/Library/Application Support/kmcc-note/seen_posts.txt`를 저장소 `seen_posts.txt`에 복사해 commit
3. `.github/workflows/scraper.yml`의 `schedule` 주석 해제 후 commit
