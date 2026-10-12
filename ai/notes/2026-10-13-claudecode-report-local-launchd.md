# 보고: kmcc-note 맥 launchd 내재화

작성자: claudecode
날짜: 2026-10-13
대상: ai/notes/2026-10-13-claude-handoff-local-launchd.md

## 확인된 원인
- GitHub Actions 계정 비활성화로 schedule 실행이 2026-09-23 12:48 UTC(seen_posts.txt 마지막 commit) 이후 중단.
- workflow는 scraper.yml 하나. cron(UTC) '13 2 * * 1-5', '13 7 * * 1-5' → KST 월-금 11:13, 16:13 (9시간 더해도 날짜가 넘어가지 않아 요일 그대로). plist도 하나로 둔다.
- Python 3.12, pip install -r requirements.txt, python -m src.main, 이후 seen_posts.txt를 commit. secrets 6개: SMTP_USER, SMTP_APP_PASSWORD, MAIL_TO, GEMINI_API_KEY, NOTION_TOKEN, NOTION_DATABASE_ID. vars 없음. dispatch 입력 test_boards → TEST_BOARDS.
- 상태 파일 경로는 src/storage.py에 "seen_posts.txt"로 고정되어 있어 환경변수 지원이 필요했다.
- 저장소에 테스트가 없다. dry-run 모드도 없다. SKIP_MAIL=1은 메일만 끄고 노션 적재와 Gemini 호출은 그대로다.
- 코드가 datetime.now()+9h로 KST를 계산한다(UTC runner 가정). 맥에서 그대로 돌리면 오후 실행의 날짜가 하루 밀리므로 run.sh가 TZ=UTC로 실행한다.
- 맥에 Python 3.12가 없다. 시스템 /usr/bin/python3 = 3.9.6만 있고 brew python, uv, pyenv 없음. 지시대로 설치하지 않았다.
- 시스템 의존성: PDF/HWP/HWPX 추출은 pdfplumber, olefile, zipfile로 순수 Python이라 별도 도구 불필요. curl_cffi는 arm64 wheel 제공.

## 변경 파일
- src/storage.py: SEEN_FILE 환경변수로 경로 재정의 (기본값 seen_posts.txt 유지)
- tests/__init__.py, tests/test_storage.py (신규, unittest)
- local/run.sh, local/install.sh, local/uninstall.sh, local/com.xmfldksl.kmcc-note.plist.template, local/README.md (신규)
- .env.local.example (신규), .gitignore(.env.local 추가, 누락된 줄바꿈 수정), README.md(local/README.md 안내 한 줄)
- .github/workflows/scraper.yml: schedule 주석 처리, workflow_dispatch 유지, 상단 안내 주석

## 수정 내용
- run.sh: .env.local을 set -a로 로드, KEY=VALUE 인자를 그 실행에만 적용(로그에는 키만), .venv Python으로 src.main 실행, requirements.txt가 바뀐 경우만 pip install, 상태 파일 기본값 ~/Library/Application Support/kmcc-note/seen_posts.txt, 상태 파일이 없으면 exit 66(전부 신규 발송 방지), mkdir lock, 날짜별 로그와 종료 코드. "발송 기록 커밋" 단계는 로컬에서 수행하지 않는다.
- plist: launchd Weekday는 범위를 받지 않아 요일 5개 × 시각 2개 = 10개 항목. RunAtLoad false. 잠자기 중 놓친 예약은 깨어나면 1회 실행된다.
- install.sh: python3.12를 PATH, brew, python.org, pyenv, uv에서 찾고 없으면 설치하지 않고 exit 2. .venv 생성과 의존성 설치, 상태 파일이 없을 때만 seen_posts.txt 복사, plist 치환 후 bootstrap.

## 테스트 결과
- 관련 테스트: python3 -m unittest discover -s tests → 4건 통과 (시스템 Python 3.9.6).
- 전체 테스트: 기존 테스트 없음. src 전체 compileall 통과.
- run.sh 스모크(스크래치 venv 3.9, 더미 비밀값, 스크래치 로그·상태 경로): TEST_BOARDS=__none__ SKIP_MAIL=1로 게시판 0개 실행 → 종료 코드 0, 상태 파일 내용 동일, 로그에 비밀값 미노출, 저장소 seen_posts.txt 변경 없음. 상태 파일 없음 66, env 없음 78, 잘못된 인자 64, lock 중복 0 확인. 렌더링한 plist plutil -lint OK.
- 실행 환경: 로컬
- 미수행: install.sh(Python 3.12 없음 + 사용자 확인 필요), 실제 수집·발송 1회.

## Git
- branch: main
- commit: 9e2f4ad(handoff), ade5537(상태 경로), 07f97f0(local runner), 61b43b2(workflow pause), 보고 commit은 CONTEXT 갱신과 함께
- Pull Request: 없음
- GitHub Actions: 비활성화 상태, schedule 주석 처리됨

## 남은 제한사항
- Python 3.12 설치 전에는 install.sh가 실패한다. 설치는 사용자가 한다. (예: brew install python@3.12)
- 첫 실행 발송량: 정기 실행은 게시판 12개의 1페이지, 최근 7일(LOOKBACK_DAYS) 글만 보므로 2026-09-24~10-05 글은 정기 실행으로는 수집되지 않는다. 사전 추정은 목록 크롤링이 필요해 수행하지 않았다. 선택지: (1) 그대로 정기 실행(최근 7일만), (2) BACKFILL_FROM=2026-09-24로 1회 소급(중단 기간 전부 발송, Gemini 한도에 걸리면 다음 실행에서 이어짐), (3) 발송 없이 상태만 갱신은 코드에 없음(SKIP_MAIL=1이어도 노션 적재와 Gemini 호출은 수행). 사용자 선택 필요.
- 로컬 상태와 저장소 seen_posts.txt는 분리되어 시간이 지나면 달라진다. Actions 복구 시 local/README.md 절차대로 되돌린다.
- 맥 잠자기·전원 설정은 변경하지 않았다.

## 사용자가 할 일
1. Python 3.12 설치 (brew install python@3.12 등)
2. cp .env.local.example .env.local 후 값 입력
3. 첫 실행 방식 선택 (위 선택지 1~3)
4. local/install.sh 실행 허가. 확인: launchctl print gui/$(id -u)/com.xmfldksl.kmcc-note
5. 전원 연결 시 잠자기 방지 설정 (시스템 설정 > 배터리 > 옵션)
6. 다음 평일 11:13 또는 16:13 이후 ~/Library/Logs/kmcc-note/YYYY-MM-DD.log에 "종료 코드=0" 확인

## 정리
- 임시 파일 또는 workflow 유지/삭제: 스크래치 디렉터리만 사용, 저장소에 임시 파일 없음. workflow는 schedule 주석 상태로 유지.
