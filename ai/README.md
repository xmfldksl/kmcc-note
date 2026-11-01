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
- Codex, Claude Code: 작업 시작 전 git pull로 원격 변경을 받은 뒤 직접 commit한다.
- Claude 채팅: GitHub MCP 커넥터로 ai/를 직접 읽고 commit한다. 커넥터를 쓸 수 없으면 ChatGPT 채팅과 같은 방법을 쓴다.
- ChatGPT 채팅: 템플릿 형식으로 문서 전체를 출력한다. Claude Code 또는 Codex를 쓸 수 있으면 "아래 내용을 ai/notes/파일명으로 저장하고 CONTEXT.md의 최신 문서를 갱신한 뒤 commit"으로 위임하고, 쓸 수 없으면 사용자가 GitHub 웹 또는 vscode.dev로 반영한다.

## 리뷰 흐름
작업한 에이전트가 review/YYYY-MM-DD-주제 브랜치에 코드 변경과 review-request 문서를 commit한다.
리뷰어는 review 문서를 작성하고, 작업 에이전트가 반영한 뒤 report를 쓴다.
리뷰어가 저장소를 직접 읽지 못하면 review-request에 diff 전문을 포함한다.

## 채팅 아카이브
한도가 끝난 뒤에는 요약을 만들 수 없으므로 작업 단위가 끝날 때마다 chat-archive 형식으로 남긴다.
새 채팅은 CONTEXT.md와 해당 아카이브만 읽고 재개한다.

## 단축 명령
사용자가 아래 단어로 지시하면 규칙대로 파일명, 날짜, 작성자, 브랜치를 채워 수행한다. "최신"은 CONTEXT.md의 최신 문서 항목을 따른다.
- 상태: CONTEXT.md와 최신 report를 읽고 현재 상태와 다음 할 일을 보고한다. 파일을 수정하지 않는다.
- 지시 주제: 채팅이 작업 지시 문서(handoff 형식)를 작성해 ai/notes/에 commit하고 CONTEXT.md의 최신 문서를 갱신한다.
- 수행: 코딩 에이전트가 pull 후 최신 지시 문서를 읽고 수행하며, report를 쓰고 CONTEXT.md를 갱신해 push한다.
- 리뷰요청: 코딩 에이전트가 review/YYYY-MM-DD-주제 브랜치에 변경과 review-request를 commit, push한다. 리뷰어는 지시가 없으면 claude다.
- 리뷰: 리뷰어가 최신 review-request와 변경 파일을 읽고 review 문서를 같은 브랜치에 commit한다. Codex는 파일을 수정하지 않고 검토만 한다.
- 반영: 코딩 에이전트가 pull 후 최신 review를 읽고 반영하며, 테스트 후 report를 쓰고 push한다.
- 결정 내용: DECISIONS.md에 추가하고 CONTEXT.md 최근 결정에 반영해 commit한다.
- 아카이브: 채팅이 chat-archive 문서를 ai/chats/에 commit하고 CONTEXT.md의 아카이브 항목을 갱신한다.
