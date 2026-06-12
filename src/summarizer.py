import json
import re
import time
import requests
from src.config import (
    GEMINI_API_KEY,
    GEMINI_MODELS,
    GEMINI_CALL_INTERVAL,
    MAX_EXTRACT_CHARS,
    SKIP_SUMMARY_PATTERNS,
)
from src.attachment import get_document_texts

# 일일 한도(RPD)가 소진된 모델 목록 / 전 모델 소진 플래그
_exhausted_models = set()
QUOTA_EXHAUSTED = False

PROMPT_TEMPLATE = """다음은 한국 방송미디어통신위원회(KMCC) 게시글에 첨부된 문서들입니다.

게시판: {board}
게시글 제목: {title}

아래 문서 내용을 한국어로 요약해 주세요.
- 핵심 결정사항, 안건, 일정, 대상 사업자를 중심으로 정리
- 문서가 여러 개면 각 문서를 【문서명】 제목 아래 구분해 요약
- 문서당 5개 이내의 짧은 문장 또는 항목으로 작성
- 순수 텍스트만 사용하고 마크다운, HTML 문법을 쓰지 않는다
- [cite: 숫자] 형태의 출처 표기는 모두 삭제한다
- 서론이나 맺음말 없이 요약 내용만 출력

{text}"""

MEETING_PROMPT_TEMPLATE = """다음은 한국 방송미디어통신위원회(KMCC, 방미통위) 회의 관련 게시글에 첨부된 문서들입니다.

게시판: {board}
게시글 제목: {title}

아래 문서 내용을 부서 공유 메일용으로 요약해 주세요. 형식 규칙을 반드시 지켜주세요.

[형식 규칙]
1. 순수 텍스트와 특수기호만 사용한다. 마크다운, HTML, 굵기 표시를 쓰지 않는다.
2. 한 줄은 100자를 넘기지 않는다.
3. 번호는 목록형 문법이 아니라 실제 숫자와 마침표(1. 2. 3.)로 적는다.
4. 문서가 여러 개면 각 문서를 【문서명】 제목 아래 구분해 요약한다.
5. 문서가 특정 차수의 회의(의사일정, 회의록, 속기록, N차 위원회 등) 관련이면:
   첫 줄을 [방미통위 N차 회의] 형태로 쓴다 (차수 확인 불가 시 [방미통위 회의]).
   이어서 "1. 일시 : ", "2. 주요 안건 : 총 N건", "3. 안건 목록" 순서로 쓴다.
   주요 안건 수는 의결사항과 보고사항 개수를 합친 수로 적는다.
   안건 목록의 각 안건은 원문자 번호(① ② ③)로 시작하고
   의결사항은 제목 끝에 "(의결)", 보고사항은 제목 끝에 "(보고)"를 붙인다.
   각 안건의 바로 다음 줄에 "- "로 시작하는 핵심 내용 한 줄을 반드시 덧붙인다.
   회의 결과(의결, 부결, 보류 등)가 문서에 있으면 해당 안건 줄에 그 결과를 포함한다.
6. 문서가 특정 차수의 회의와 관련이 없으면:
   숫자와 마침표(1. 2.)로 항목을 나누고, 둘째 깊이는 원문자 번호(① ② ③),
   셋째 깊이부터는 "- "로 시작해 정리한다. 결과에 관한 내용은 반드시 포함한다.
7. [cite: 숫자] 형태의 출처 표기는 모두 삭제한다.
8. 인사말, 맺음말, 부가 설명 없이 요약 본문만 출력한다.

{text}"""


def _is_meeting_related(item, extra_text=""):
    """의사일정 게시판 글이거나 회의 차수/회의록/속기록 관련 문서인지 판별한다."""
    if item.get('board_name') == "의사일정":
        return True
    text = f"{item.get('title', '')} {extra_text}"
    if re.search(r'제?\s*\d+\s*차\s*.{0,10}(위원회|회의)', text):
        return True
    return any(k in text for k in ("회의록", "속기록", "의사일정"))


def _call_model(model, prompt):
    """특정 모델을 호출한다. 반환: (요약문 또는 None, 한도소진 여부)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    rate_limited = False
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    return text, False
                print(f"    -> [{model}] 응답이 비어있음")
            elif resp.status_code == 429:
                rate_limited = True
                print(f"    -> [{model}] 속도 제한(429), 60초 대기 (시도 {attempt}/{max_retries})")
                time.sleep(60)
                continue
            elif resp.status_code >= 500:
                print(f"    -> [{model}] 서버 오류({resp.status_code}), 30초 대기 (시도 {attempt}/{max_retries})")
                time.sleep(30)
                continue
            else:
                print(f"    -> [{model}] 오류 (HTTP {resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"    -> [{model}] 호출 에러 (시도 {attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(10)
    return None, rate_limited


def _call_gemini(prompt):
    """모델 체인을 따라 호출한다. 앞 모델의 일일 한도가 소진되면 다음 모델로 전환.

    모든 모델이 한도 소진이면 QUOTA_EXHAUSTED를 켠다.
    """
    global QUOTA_EXHAUSTED

    for model in GEMINI_MODELS:
        if model in _exhausted_models:
            continue
        result, rate_limited = _call_model(model, prompt)
        if result:
            return result
        if rate_limited:
            _exhausted_models.add(model)
            print(f"    -> [{model}] 일일 한도 소진으로 판단, 다음 모델로 전환")
            continue
        return None  # 한도 외의 오류는 모델 전환 없이 실패 처리

    if all(m in _exhausted_models for m in GEMINI_MODELS):
        QUOTA_EXHAUSTED = True
        print("    -> [경고] 모든 Gemini 모델의 일일 한도 소진")
    return None


def summarize(item):
    """게시글의 요약문을 생성한다 (게시글당 Gemini 호출 1회).

    - 모든 첨부 문서를 하나의 프롬프트로 묶어 한 번에 요약 (호출량 절감)
    - 양식/서식 문서는 요약 대상에서 제외 (노션 파일 첨부는 유지)
    - 문서가 없거나 전부 제외되면 게시글 본문으로 요약
    - 전 모델 한도 소진 시 None 반환 → main이 기록 없이 중단해 다음 실행에서 이어감
    """
    item['summary_docs'] = []

    if QUOTA_EXHAUSTED:
        return None

    documents = get_document_texts(item)

    # 노션 첨부/링크용 문서 기록 (요약 제외 문서 포함)
    for doc in documents:
        item['summary_docs'].append({
            'doc_name': doc['doc_name'],
            'file_name': doc['file_name'],
            'url': doc['url'],
            'data': doc.get('data'),
        })

    # 요약 대상 문서 선별 (양식/서식 제외)
    target_docs = [
        d for d in documents
        if not any(p in d['doc_name'] for p in SKIP_SUMMARY_PATTERNS)
    ]
    for d in documents:
        if d not in target_docs:
            print(f"    -> 요약 제외 (양식/서식): {d['doc_name'][:20]}")

    # --- 1순위: 첨부 문서 통합 요약 (게시글당 1회 호출) ---
    if target_docs:
        doc_names = " ".join(d['doc_name'] for d in target_docs)
        template = (
            MEETING_PROMPT_TEMPLATE
            if _is_meeting_related(item, doc_names)
            else PROMPT_TEMPLATE
        )

        # 문서들을 하나의 텍스트로 결합 (전체 길이 상한 적용)
        combined = ""
        per_doc_limit = max(MAX_EXTRACT_CHARS // len(target_docs), 3000)
        for d in target_docs:
            combined += f"\n\n===== 문서: {d['doc_name']} =====\n{d['text'][:per_doc_limit]}"
        combined = combined[:MAX_EXTRACT_CHARS]

        prompt = template.format(
            board=item.get('board_name', ''),
            title=item.get('title', ''),
            text=f"문서 내용:{combined}",
        )
        print(f"    -> Gemini 통합 요약 요청 (문서 {len(target_docs)}개)")
        result = _call_gemini(prompt)
        time.sleep(GEMINI_CALL_INTERVAL)

        if QUOTA_EXHAUSTED:
            return None
        if result:
            return result

    # --- 2순위: 게시글 본문 요약 ---
    content = (item.get('content') or '').strip()
    if content and not QUOTA_EXHAUSTED:
        template = (
            MEETING_PROMPT_TEMPLATE
            if _is_meeting_related(item, "게시글 본문")
            else PROMPT_TEMPLATE
        )
        prompt = template.format(
            board=item.get('board_name', ''),
            title=item.get('title', ''),
            text=f"문서 내용:\n{content[:10000]}",
        )
        print("    -> Gemini 요약 요청: 게시글 본문")
        result = _call_gemini(prompt)
        time.sleep(GEMINI_CALL_INTERVAL)
        if QUOTA_EXHAUSTED:
            return None
        if result:
            return result

    # --- 3순위: 본문 앞부분 (기존 방식) ---
    print("    -> Gemini 요약 실패, 본문 앞부분으로 대체")
    return content[:500] if content else "(내용 없음)"

# END OF FILE