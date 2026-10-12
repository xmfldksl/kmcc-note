# CONTEXT

최종 갱신: 2026-10-13 / 작성자: claudecode
(덮어쓰는 유일한 파일. 50줄 이내 유지.)

## 현재 목표
- GitHub Actions 비활성화 동안 맥 launchd로 예약 실행 유지

## 진행 중 작업
- 로컬 실행 전환: 코드·스크립트 commit 완료. install.sh 실행(launchd 등록)과 첫 실행은 사용자 확인 대기.

## 최근 결정
- Actions 비활성화로 맥 launchd 내재화, 복구 시 환원 (ai/DECISIONS.md 참조)
- ai/ 공유 공간 도입

## 미해결 이슈
- Actions 복구 시 되돌리기(schedule 주석 해제, launchd 해제). 절차는 local/README.md
- 맥에 Python 3.12 없음 (사용자 설치 필요)
- 첫 실행 발송 방식 선택 필요 (보고의 남은 제한사항 참조)

## 다음 할 일
- 사용자: Python 3.12 설치, .env.local 값 입력, 첫 실행 방식 선택, local/install.sh 실행, 잠자기 방지 설정, 첫 예약 실행 로그 확인
- Claude 프로젝트 지식에 이 저장소의 ai/ 폴더 추가 후 Sync (사용자)

## 최신 문서
- 인수인계: ai/notes/2026-10-13-claude-handoff-local-launchd.md
- 리뷰: 없음
- 보고: ai/notes/2026-10-13-claudecode-report-local-launchd.md
- 아카이브: 없음
