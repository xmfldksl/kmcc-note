# CONTEXT

최종 갱신: 2026-10-28 / 작성자: claudecode
(덮어쓰는 유일한 파일. 50줄 이내 유지.)

## 현재 목표
- GitHub Actions 비활성화 동안 맥 launchd로 예약 실행 유지

## 진행 중 작업
- 로컬 실행 전환 완료, 예약 실행 검증 대기. launchd 등록·백필(2026-09-24~) 1회 완료, 평일 10:30/17:00 KST 예약.

## 최근 결정
- GitHub Actions 삭제 (ai/DECISIONS.md 참조)
- 로컬 예약 시각을 평일 10:30/17:00 KST로 변경 (ai/DECISIONS.md 참조)
- Actions 비활성화로 맥 launchd 내재화, 복구 시 환원 (ai/DECISIONS.md 참조)
- ai/ 공유 공간 도입

## 미해결 이슈
- 잠자기 방지는 sentinel-o-car 운영 설정에 의존. 센티넬 해제 시 재확인

## 다음 할 일
- 사용자: 다음 평일 10:30/17:00 이후 ~/Library/Logs/kmcc-note/YYYY-MM-DD.log에서 "종료 코드=0" 확인
- Claude 프로젝트 지식에 이 저장소의 ai/ 폴더 추가 후 Sync (사용자)

## 최신 문서
- 인수인계: ai/notes/2026-10-13-claude-handoff-local-launchd.md
- 리뷰: 없음
- 보고: ai/notes/2026-10-13-claudecode-report-local-launchd.md (후속 확인 절 포함)
- 아카이브: 없음
