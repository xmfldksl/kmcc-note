# DECISIONS

추가만 한다. 한 줄 형식: 날짜 | 작성자 | 결정 | 근거 | 관련 문서

- 2026-09-25 | claudecode | 4개 도구 공유 공간을 ai/ 폴더로 운영 | 도구 간 대화가 공유되지 않아 저장소를 공용 기억으로 사용 | ai/README.md
- 2026-10-13 | claudecode | Actions 비활성화로 맥 launchd 내재화, 복구 시 환원 | 2026-09-24부터 계정 단위 Actions 중단, 예약·비밀값·상태를 맥에서 대체 | ai/notes/2026-10-13-claudecode-report-local-launchd.md
- 2026-10-13 | claudecode | 로컬 launchd 예약 시각을 평일 10:30/17:00 KST로 변경 | 로컬 실행은 Actions 혼잡 회피 지터(x:13)가 불필요. workflow cron은 유지, Actions 복구 시 재결정 | local/com.xmfldksl.kmcc-note.plist.template
- 2026-10-28 | claudecode | GitHub Actions workflow 전부 삭제 | 예약 작업을 맥북 로컬 실행으로 이전했고 GitHub 계정 Actions 제한 중. 복구 시 git 히스토리에서 복원 가능 | .github/workflows
- 2026-11-01 | claude | Claude 채팅이 GitHub MCP 커넥터로 ai/를 직접 읽고 commit | 카드 Sync와 붙여넣기 없이 채팅과 CLI 간 공유를 자동화. CLI는 작업 전 git pull 필수 | ai/README.md
