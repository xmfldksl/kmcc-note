# 인수인계: kmcc-note 맥 launchd 내재화

작성자: claude
날짜: 2026-10-13
대상: claudecode

## 프로젝트
- 경로: $HOME/Projects/kmcc-note
- 저장소: git remote -v로 확인 (xmfldksl/kmcc-note로 추정)
- 기준 branch: main. branch 규칙은 CLAUDE.md와 ai/CONTEXT.md에서 확인하고, 규칙이 없으면 작업 전에 사용자에게 확인한다.

## 작업 목적
GitHub 계정의 Actions가 2026-09-24부터 계정 단위로 비활성화되어 예약 workflow가 멈춘 상태다. GitHub Actions가 맡던 예약, 비밀값 보관, 상태 저장(commit 또는 cache) 세 가지를 맥 안에서 대체해 Actions 없이 같은 주기로 동작하게 한다. Actions가 복구되면 되돌릴 수 있어야 한다.

## 참고 구현
- $HOME/Projects/sentinel-o-car/local/ 에 같은 목적의 구현이 있으면 읽기 전용으로 참고해 파일 구성과 스크립트 방식을 맞춘다. 그 저장소는 수정하지 않는다. 없으면 이 문서만으로 진행한다.
- sentinel-o-car의 ai/notes/ 에 local-launchd report가 있으면 거기 기록된 문제점과 해결책을 먼저 반영한다.

## 먼저 확인할 파일
- .github/workflows/ 아래 모든 workflow: cron 주기, 실행 단계, Python 버전, 의존성 설치 방식, secrets와 vars 이름, 상태 저장 단계(commit, cache, artifact), workflow_dispatch 입력, runs-on 값
- README, REQUIREMENTS.md, CLAUDE.md, ai/CONTEXT.md
- requirements.txt 또는 pyproject.toml, 진입점 스크립트
- 상태 파일(중복 발송 방지용 기록 등)이 있는지, 경로가 코드 어디서 정해지는지, 환경변수로 바꿀 수 있는지
- 테스트 모드나 dry-run 유무, 알림 채널(Telegram, 이메일, Notion)별 전송을 끄는 방법
- 첨부 요약에 쓰는 외부 API와 시스템 의존성(PDF, HWP 변환 도구 등)이 맥에 필요한지
- .gitignore

## 수정 범위와 제한
- 현재 구현을 먼저 읽고 최소 변경한다. 필드명, 함수명, 환경변수명은 추측하지 않고 코드에서 확인한다.
- local/ 폴더를 새로 만들고 다음을 둔다.
  - local/run.sh: 저장소 경로로 이동, .env.local을 읽어 환경변수로 노출(set -a; source; set +a), 저장소 안 .venv의 Python으로 workflow 단계를 같은 순서로 실행, 로그를 $HOME/Library/Logs/kmcc-note/YYYY-MM-DD.log에 추가, 종료 코드 기록. set -euo pipefail 사용. 이전 실행이 끝나지 않았으면 겹치지 않게 lock 처리.
  - local/com.xmfldksl.kmcc-note.plist.template: launchd 에이전트. StartCalendarInterval은 workflow cron(UTC)을 KST로 변환해 같은 시각들로, RunAtLoad는 false, 표준 출력과 오류는 위 로그 경로로. workflow가 여러 개면 각각의 주기를 보고 plist를 하나로 할지 나눌지 판단해 근거와 함께 보고한다.
  - local/install.sh: .venv가 없으면 workflow와 같은 Python 버전으로 만들고 의존성을 설치, 템플릿의 경로를 현재 환경 값으로 치환해 $HOME/Library/LaunchAgents/에 복사, launchctl bootstrap gui/$(id -u)로 등록. local/uninstall.sh: bootout으로 해제.
  - local/README.md: 설치, 해제, 로그 위치, 수동 실행, Actions 복구 시 되돌리는 순서를 짧게.
- workflow와 같은 Python 버전이 맥에 없으면 임의로 설치하지 말고 사용자에게 보고한다.
- 비밀값: workflow에서 secrets.와 vars.로 참조하는 이름을 모두 추출해 .env.local.example에 이름만 나열한다. .env.local과 .venv를 .gitignore에 추가한다. 실제 값은 사용자가 채우며 로그에 값이 찍히지 않게 한다.
- 상태 파일: 있다면 로컬 실행이 저장소 안의 추적 파일을 건드리지 않게 한다. 코드가 경로를 환경변수로 받을 수 있으면 그것을 쓰고, 없으면 경로를 환경변수로 바꿀 수 있는 최소 변경을 넣되 기본값은 현행 그대로 두어 workflow와 호환되게 하고 테스트를 추가한다. 로컬 상태 경로는 $HOME/Library/Application Support/kmcc-note/ 아래로 하고, install.sh가 현재 상태 파일을 그 위치로 한 번 복사해 이어받게 한다. 이미 있으면 덮어쓰지 않는다.
- 상태 이어받기 주의: 2026-09-24 이후 중단 기간의 게시물이 첫 실행에서 한꺼번에 발송될 수 있다. 코드에서 첫 실행 시 예상 발송량을 가늠할 방법을 확인하고, 처리 방안(그대로 발송, 상한 적용, 발송 없이 상태만 갱신)을 사용자에게 제시해 선택받는다.
- workflow: 예약 workflow의 schedule 트리거만 주석 처리하고 workflow_dispatch는 유지한다. 상단에 "로컬 launchd로 실행 중, Actions 복구 시 주석 해제" 주석을 남긴다. Actions 복구 시 이중 실행을 막기 위함이다. 이 변경은 별도 commit으로 한다.
- launchd 등록(install.sh 실행)은 사용자 확인 후에 한다. 맥의 전원이나 잠자기 설정은 변경하지 말고 안내만 한다.

## 금지 작업
- 비밀값, Token, Chat ID, 이메일 비밀번호, Notion 키를 저장소 파일이나 로그에 기록
- 상태 파일을 commit하거나 삭제
- 기존 테스트 삭제 또는 assertion 약화
- 관련 없는 리팩터링
- 사용자 확인 없이 실제 수집과 Telegram, 이메일, Notion 전송 실행
- sentinel-o-car 저장소 수정, 전역 Git 설정 변경

## 테스트 방법
- 기존 테스트 전체 통과(실행 명령은 workflow 또는 README에서 확인).
- local/run.sh를 테스트 모드나 dry-run으로 수동 실행해 실제 전송 없이 끝까지 도는지 확인한다. 그런 모드가 없으면 그 사실을 보고하고, 실제 1회 실행은 사용자 확인 후 진행한다.
- install.sh 실행 후 launchctl print gui/$(id -u)/com.xmfldksl.kmcc-note 로 등록 상태를 확인한다. 다음 예약 시각 이후 로그의 정상 종료는 사용자가 확인한다.
- git status로 작업 트리가 clean인지, .env.local과 .venv가 무시되는지(git check-ignore) 확인한다.

## commit 메시지
- feat: add local launchd runner / 로컬 launchd 실행 추가
- feat: allow state file path override / 상태 파일 경로 환경변수 지원 (코드 변경이 필요한 경우만)
- chore: pause scheduled workflow while running locally / 로컬 실행 중 예약 workflow 중지
- docs(ai): add local runner report / 로컬 실행 보고 추가

## 완료 시
- ai/notes/2026-10-13-claudecode-report-local-launchd.md 작성
- ai/CONTEXT.md 갱신: 진행 중 작업에 로컬 실행 전환, 미해결 이슈에 "Actions 복구 시 되돌리기(schedule 주석 해제, launchd 해제)" 기록
- ai/DECISIONS.md에 "Actions 비활성화로 맥 launchd 내재화, 복구 시 환원" 한 줄 추가
- ai/ 폴더가 없으면 만들지 말고 그 사실을 보고한다.
- 보고: 변경 파일, 테스트 결과, commit hash, 확인한 cron 주기와 변환한 KST 시각, 사용자가 할 일(.env.local 값 입력, 전원 연결 시 잠자기 방지 설정, 첫 예약 실행 확인)
