import json
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
- 서론이나 맺음말 없이 요약 내용만 출력

문서 내용:
{text}"""


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
            else:
                print(f"    -> Gemini 오류 (HTTP {resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"    -> Gemini 호출 에러 (시도 {attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(10)
    return None


def summarize(item):
    """게시글의 요약문을 생성한다.

    1순위: 첨부 문서(PDF/HWPX)별 Gemini 요약 (문서가 여러 개면 각각 요약 후 합침)
    2순위: 게시글 본문 Gemini 요약
    3순위: 게시글 본문 앞 500자 (기존 방식)
    부수 효과: item['summary_docs']에 문서별 요약·원본 링크를 저장 (메일/노션용)
    """
    item['summary_docs'] = []

    # --- 1순위: 첨부 문서 요약 ---
    documents = get_document_texts(item)
    if documents:
        sections = []
        for doc in documents:
            prompt = PROMPT_TEMPLATE.format(
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
        prompt = PROMPT_TEMPLATE.format(
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