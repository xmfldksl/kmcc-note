import json
import re
import time
import requests
from src.config import (
    GEMINI_API_KEY,
    GEMINI_API_URL,
    GEMINI_CALL_INTERVAL,
)
from src.attachment import get_document_texts

PROMPT_TEMPLATE = """다음은 한국 방송미디어통신위원회(KMCC) 게시글의 문서 내용입니다.

게시판: {board}
게시글 제목: {title}
문서명: {doc_name}

아래 문서 내용을 한국어로 요약해 주세요.
- 핵심 결정사항, 안건, 일정, 대상 사업자를 중심으로 정리
- 5개 이내의 짧은 문장 또는 항목으로 작성
- 순수 텍스트만 사용하고 마크다운, HTML 문법을 쓰지 않는다
- [cite: 숫자] 형태의 출처 표기는 모두 삭제한다
- 서론이나 맺음말 없이 요약 내용만 출력

문서 내용:
{text}"""

MEETING_PROMPT_TEMPLATE = """다음은 한국 방송미디어통신위원회(KMCC, 방미통위) 회의 관련 문서입니다.

게시판: {board}
게시글 제목: {title}
문서명: {doc_name}

아래 문서 내용을 부서 공유 메일용으로 요약해 주세요. 형식 규칙을 반드시 지켜주세요.

[형식 규칙]
1. 순수 텍스트와 특수기호만 사용한다. 마크다운, HTML, 굵기 표시를 쓰지 않는다.
2. 한 줄은 100자를 넘기지 않는다.
3. 번호는 목록형 문법이 아니라 실제 숫자와 마침표(1. 2. 3.)로 적는다.
4. 문서가 특정 차수의 회의(의사일정, 회의록, 속기록, N차 위원회 등) 관련이면:
   첫 줄을 [방미통위 N차 회의] 형태로 쓴다 (차수 확인 불가 시 [방미통위 회의]).
   이어서 "1. 일시 : ", "2. 주요 안건 : 총 N건", "3. 안건 목록" 순서로 쓴다.
   주요 안건 수는 의결사항과 보고사항 개수를 합친 수로 적는다.
   안건 목록의 각 안건은 원문자 번호(① ② ③)로 시작하고
   의결사항은 제목 끝에 "(의결)", 보고사항은 제목 끝에 "(보고)"를 붙인다.
   각 안건의 바로 다음 줄에 "- "로 시작하는 핵심 내용 한 줄을 반드시 덧붙인다.
   회의 결과(의결, 부결, 보류 등)가 문서에 있으면 해당 안건 줄에 그 결과를 포함한다.
5. 문서가 특정 차수의 회의와 관련이 없으면:
   숫자와 마침표(1. 2.)로 항목을 나누고, 둘째 깊이는 원문자 번호(① ② ③),
   셋째 깊이부터는 "- "로 시작해 정리한다. 결과에 관한 내용은 반드시 포함한다.
6. [cite: 숫자] 형태의 출처 표기는 모두 삭제한다.
7. 인사말, 맺음말, 부가 설명 없이 요약 본문만 출력한다.

문서 내용:
{text}"""


def _is_meeting_related(item, doc_name=""):
    """의사일정 게시판 글이거나 회의 차수/회의록/속기록 관련 문서인지 판별한다."""
    if item.get('board_name') == "의사일정":
        return True
    text = f"{item.get('title', '')} {doc_name}"
    if re.search(r'제?\s*\d+\s*차\s*.{0,10}(위원회|회의)', text):
        return True
    return any(k in text for k in ("회의록", "속기록", "의사일정"))


def _call_gemini(prompt):
    """Gemini API를 호출해 요약 텍스트를 반환한다. 실패 시 None."""
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                GEMINI_API_URL, headers=headers,
                data=json.dumps(payload), timeout=120
            )
            if resp.status_code == 200:
                data = resp.json()
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text
                print("    -> Gemini 응답이 비어있음")
            elif resp.status_code == 429:
                # 무료 등급 분당 한도 초과: 대기 후 재시도
                print(f"    -> Gemini 속도 제한(429), 60초 대기 (시도 {attempt}/{max_retries})")
                time.sleep(60)
                continue
            elif resp.status_code >= 500:
                # 서버 과부하/일시 장애: 30초 대기 후 재시도
                print(f"    -> Gemini 서버 오류({resp.status_code}), 30초 대기 (시도 {attempt}/{max_retries})")
                time.sleep(30)
                continue
            else:
                print(f"    -> Gemini 오류 (HTTP {resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"    -> Gemini 호출 에러 (시도 {attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(10)
    return None


def summarize(item):
    """게시글의 요약문을 생성한다.

    1순위: 첨부 문서(PDF/HWPX/HWP)별 Gemini 요약 (문서가 여러 개면 각각 요약 후 합침)
    2순위: 게시글 본문 Gemini 요약
    3순위: 게시글 본문 앞 500자 (기존 방식)
    회의 관련 문서(의사일정/회의록/속기록/N차 위원회)는 부서 공유 양식을 적용한다.
    부수 효과: item['summary_docs']에 문서별 요약·원본 링크를 저장 (메일/노션용)
    """
    item['summary_docs'] = []

    # --- 1순위: 첨부 문서 요약 ---
    documents = get_document_texts(item)
    if documents:
        sections = []
        for doc in documents:
            template = (
                MEETING_PROMPT_TEMPLATE
                if _is_meeting_related(item, doc['doc_name'])
                else PROMPT_TEMPLATE
            )
            prompt = template.format(
                board=item.get('board_name', ''),
                title=item.get('title', ''),
                doc_name=doc['doc_name'],
                text=doc['text'],
            )
            print(f"    -> Gemini 요약 요청: {doc['doc_name'][:20]}")
            result = _call_gemini(prompt)
            time.sleep(GEMINI_CALL_INTERVAL)

            if result:
                item['summary_docs'].append({
                    'doc_name': doc['doc_name'],
                    'file_name': doc['file_name'],
                    'url': doc['url'],
                    'summary': result,
                })
                if len(documents) > 1:
                    sections.append(f"【{doc['doc_name']}】\n{result}")
                else:
                    sections.append(result)
        if sections:
            return "\n\n".join(sections)

    # --- 2순위: 게시글 본문 요약 ---
    content = (item.get('content') or '').strip()
    if content:
        template = (
            MEETING_PROMPT_TEMPLATE
            if _is_meeting_related(item, "게시글 본문")
            else PROMPT_TEMPLATE
        )
        prompt = template.format(
            board=item.get('board_name', ''),
            title=item.get('title', ''),
            doc_name="게시글 본문",
            text=content[:10000],
        )
        print("    -> Gemini 요약 요청: 게시글 본문")
        result = _call_gemini(prompt)
        time.sleep(GEMINI_CALL_INTERVAL)
        if result:
            return result

    # --- 3순위: 본문 앞부분 (기존 방식) ---
    print("    -> Gemini 요약 실패, 본문 앞부분으로 대체")
    return content[:500] if content else "(내용 없음)"

# END OF FILE