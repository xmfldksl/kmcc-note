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

# 응답에서 전체 요약과 피드 요약을 구분하는 표지
FULL_MARKER = "[전체요약]"
FEED_MARKER = "[피드요약]"

PROMPT_TEMPLATE = """다음은 한국 방송미디어통신위원회(KMCC) 게시글에 첨부된 문서들입니다.

게시판: {board}
게시글 제목: {title}
핵심 키워드: {keywords}

아래 문서 내용을 두 가지로 요약해 주세요. 반드시 아래 형식을 지키세요.

[전체요약]
- 핵심 결정사항, 안건, 일정, 대상 사업자를 중심으로 정리
- 문서가 여러 개면 각 문서를 【문서명】 제목 아래 구분해 요약
- 문서당 5개 이내의 짧은 문장 또는 항목
- 순수 텍스트만 사용(마크다운/HTML 금지), [cite: 숫자] 표기 삭제

[피드요약]
- SNS 피드 카드에 쓸 초압축 요약
- 3줄 이내, 각 줄은 짧게(구체적 날짜·조항번호·기관명 나열 금지)
- 무엇에 관한 글인지 한눈에 알 수 있게 핵심만
- 핵심 키워드가 있으면 그 단어를 자연스럽게 포함
- 순수 텍스트만 사용

문서 내용:
{text}"""

MEETING_PROMPT_TEMPLATE = """다음은 한국 방송미디어통신위원회(KMCC, 방미통위) 회의 관련 게시글에 첨부된 문서들입니다.

게시판: {board}
게시글 제목: {title}
핵심 키워드: {keywords}

아래 문서 내용을 두 가지로 요약해 주세요. 반드시 아래 형식을 지키세요.

[전체요약]
부서 공유 메일용 정형 요약. 형식 규칙:
1. 순수 텍스트와 특수기호만 사용(마크다운/굵기 금지). 한 줄 100자 이내.
2. 번호는 실제 숫자와 마침표(1. 2. 3.)로 표기.
3. 문서가 여러 개면 각 문서를 【문서명】 아래 구분해 요약.
4. 특정 차수 회의 관련이면: 첫 줄 [방미통위 N차 회의](차수 불명 시 [방미통위 회의]),
   이어 "1. 일시 : ", "2. 주요 안건 : 총 N건", "3. 안건 목록" 순.
   안건은 원문자(① ② ③)로 시작, 의결사항 끝에 "(의결)", 보고사항 끝에 "(보고)",
   각 안건 다음 줄에 "- " 핵심 한 줄. 회의 결과(의결/부결/보류)가 있으면 포함.
5. 차수 회의가 아니면 숫자(1. 2.)·원문자(① ②)·"- "로 정리. 결과 내용 포함.
6. [cite: 숫자] 표기 삭제. 인사말·맺음말 없이 본문만.

[피드요약]
- SNS 피드 카드에 쓸 초압축 요약
- 3줄 이내, 각 줄은 짧게(구체적 날짜·조항번호·기관명 나열 금지)
- 회의면 차수와 핵심 안건 한두 개만 짧게
- 핵심 키워드가 있으면 그 단어를 자연스럽게 포함
- 순수 텍스트만 사용

문서 내용:
{text}"""


def _is_meeting_related(item, extra_text=""):
    """의사일정 게시판 글이거나 회의 차수/회의록/속기록 관련 문서인지 판별한다."""
    if item.get('board_name') == "의사일정":
        return True
    text = f"{item.get('title', '')} {extra_text}"
    if re.search(r'제?\s*\d+\s*차\s*.{0,10}(위원회|회의)', text):
        return True
    return any(k in text for k in ("회의록", "속기록", "의사일정"))


def _split_summaries(raw):
    """모델 응답을 (전체요약, 피드요약)으로 분리한다. 표지가 없으면 전체만 채운다."""
    if not raw:
        return "", ""
    feed_idx = raw.find(FEED_MARKER)
    full_idx = raw.find(FULL_MARKER)

    if feed_idx != -1:
        full_part = raw[:feed_idx]
        feed_part = raw[feed_idx + len(FEED_MARKER):]
    else:
        full_part = raw
        feed_part = ""

    if full_idx != -1 and (feed_idx == -1 or full_idx < feed_idx):
        full_part = full_part[full_idx + len(FULL_MARKER):]

    return full_part.strip(), feed_part.strip()


def _finalize_feed(feed_text, full_text, keywords):
    """피드 요약을 3줄 이내로 정리한다.

    키워드는 프롬프트에서 '본문에 있으면 자연스럽게 포함'하도록 유도할 뿐,
    여기서 억지로 덧붙이지 않는다 (본문에 없으면 포함하지 않아도 됨).
    """
    base = feed_text or full_text
    # 빈 줄 제거 후 최대 3줄
    lines = [ln.strip() for ln in base.splitlines() if ln.strip()]
    lines = lines[:3]
    result = "\n".join(lines)

    # 길이 안전장치 (너무 길면 자름)
    if len(result) > 240:
        result = result[:240].rstrip() + "…"

    return result.strip()
    

def _call_model(model, prompt):
    """특정 모델을 호출한다. 반환: (응답문 또는 None, 한도소진 여부)"""
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
    """모델 체인을 따라 호출한다. 앞 모델의 일일 한도가 소진되면 다음 모델로 전환."""
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
        return None

    if all(m in _exhausted_models for m in GEMINI_MODELS):
        QUOTA_EXHAUSTED = True
        print("    -> [경고] 모든 Gemini 모델의 일일 한도 소진")
    return None


def summarize(item):
    """게시글의 요약문을 생성한다 (게시글당 Gemini 호출 1회).

    전체 요약과 피드용 초압축 요약(3줄 이내)을 한 번의 호출로 함께 생성한다.
    피드 요약은 item['feed_summary']에 저장된다.
    """
    item['summary_docs'] = []
    item['feed_summary'] = ""

    if QUOTA_EXHAUSTED:
        return None

    keywords = item.get('matched_keywords', [])
    keywords_str = ", ".join(keywords) if keywords else "(없음)"

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

    def _run(template, text_block):
        prompt = template.format(
            board=item.get('board_name', ''),
            title=item.get('title', ''),
            keywords=keywords_str,
            text=text_block,
        )
        raw = _call_gemini(prompt)
        time.sleep(GEMINI_CALL_INTERVAL)
        return raw

    # --- 1순위: 첨부 문서 통합 요약 (게시글당 1회 호출) ---
    if target_docs:
        doc_names = " ".join(d['doc_name'] for d in target_docs)
        template = MEETING_PROMPT_TEMPLATE if _is_meeting_related(item, doc_names) else PROMPT_TEMPLATE

        combined = ""
        per_doc_limit = max(MAX_EXTRACT_CHARS // len(target_docs), 3000)
        for d in target_docs:
            combined += f"\n\n===== 문서: {d['doc_name']} =====\n{d['text'][:per_doc_limit]}"
        combined = combined[:MAX_EXTRACT_CHARS]

        print(f"    -> Gemini 통합 요약 요청 (문서 {len(target_docs)}개)")
        raw = _run(template, combined)

        if QUOTA_EXHAUSTED:
            return None
        if raw:
            full, feed = _split_summaries(raw)
            item['feed_summary'] = _finalize_feed(feed, full, keywords)
            if full:
                return full

    # --- 2순위: 게시글 본문 요약 ---
    content = (item.get('content') or '').strip()
    if content and not QUOTA_EXHAUSTED:
        template = MEETING_PROMPT_TEMPLATE if _is_meeting_related(item, "게시글 본문") else PROMPT_TEMPLATE
        print("    -> Gemini 요약 요청: 게시글 본문")
        raw = _run(template, content[:10000])
        if QUOTA_EXHAUSTED:
            return None
        if raw:
            full, feed = _split_summaries(raw)
            item['feed_summary'] = _finalize_feed(feed, full, keywords)
            if full:
                return full

    # --- 3순위: 본문 앞부분 (기존 방식) ---
    print("    -> Gemini 요약 실패, 본문 앞부분으로 대체")
    fallback = content[:500] if content else "(내용 없음)"
    item['feed_summary'] = _finalize_feed("", fallback, keywords)
    return fallback

# END OF FILE