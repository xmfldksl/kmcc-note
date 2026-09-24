# ai/ 공유 공간

ChatGPT 채팅, Codex, Claude 채팅, Claude Code가 함께 읽고 쓰는 공간이다.
이 저장소에 commit되지 않은 결정과 상태는 없는 것으로 본다.

## 구성
- CONTEXT.md: 현재 상태 한 장. 모든 도구가 가장 먼저 읽는다. 유일하게 덮어쓰는 파일이며 50줄 이내로 유지한다.
- DECISIONS.md: 결정 기록. 추가만 한다.
- notes/: 인수인계(handoff), 리뷰 요청(review-request), 리뷰 결과(review), 완료 보고(report). 추가만 한다.
- chats/: 채팅 아카이브. 요약 중심. 추가만 한다.
- templates/: 문서 형식 5종. 새 문서는 해당 템플릿을 복사해 쓴다.

## 읽기 순서
CONTEXT.md, 그다음 CONTEXT.md에 링크된 최신 문서, 필요한 경우에만 chats/.
코딩 에이전트(Codex, Claude Code)는 지시가 없으면 chats/를 읽지 않는다.

## 쓰기 규칙
- 파일명: YYYY-MM-DD-작성자-종류-주제.md (chats/는 YYYY-MM-DD-작성자-주제.md)
- 작성자 코드: gpt, codex, claude, claudecode
- 종류: handoff, review-request, review, report
- 모든 문서 상단에 작성자와 날짜를 적는다.
- 작업을 마치면 report를 쓰고 CONTEXT.md를 갱신한다. 결정이 있으면 DECISIONS.md에 추가한다.
- ai/ 문서 변경은 코드 변경과 별도로 commit한다. 메시지 예: docs(ai): add report / 보고 추가
- 비밀값, Token, 인증 URL은 어떤 문서에도 적지 않는다. 채팅 아카이브는 저장 전에 제거한다.

## 도구별 반영 방법
- Codex, Claude Code: 직접 commit한다.
- ChatGPT 채팅, Claude 채팅: 템플릿 형식으로 문서 전체를 출력한다. Claude Code 또는 Codex를 쓸 수 있으면 "아래 내용을 ai/notes/파일명으로 저장하고 CONTEXT.md의 최신 문서를 갱신한 뒤 commit"으로 위임하고, 쓸 수 없으면 사용자가 GitHub 웹 또는 vscode.dev로 반영한다.

## 리뷰 흐름
작업한 에이전트가 review/YYYY-MM-DD-주제 브랜치에 코드 변경과 review-request 문서를 commit한다.
리뷰어는 review 문서를 작성하고, 작업 에이전트가 반영한 뒤 report를 쓴다.
리뷰어가 저장소를 직접 읽지 못하면 review-request에 diff 전문을 포함한다.

## 채팅 아카이브
한도가 끝난 뒤에는 요약을 만들 수 없으므로 작업 단위가 끝날 때마다 chat-archive 형식으로 남긴다.
새 채팅은 CONTEXT.md와 해당 아카이브만 읽고 재개한다.
