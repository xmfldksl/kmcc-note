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

# 피드용 3줄 요약을 별도로 생성할 때 쓰는 프롬프트
FEED_PROMPT_TEMPLATE = """너는 방송미디어통신위원회(방미통위) 게시판 글의 '전체요약'을 받아 노션 피드용 '3줄 요약'으로 변환하는 변환기다. 아래 규칙을 모두 지켜 요약문만 출력한다.

[출력 형식]
- 핵심만 담아 3개 구간 이내로 요약하고, 각 구간은 짧게 쓴다.
- 설명투(~합니다, ~했다, ~된다)를 쓰지 않고 명사형 줄임체로 끝맺는다(예: 의결, 보고, 추진, 완화, 부과).
- 줄바꿈 없이 한 줄로 출력한다. 세 구간을 마침표(.)로 구분하고, 마지막 구간 끝에도 마침표를 찍는다.
- 마크다운 기호(*, #, -, >, 불릿 등)와 머리표를 쓰지 않고 순수 한국어 문장만 쓴다.
- 요약문만 출력한다. 머리말, 따옴표, 부가 설명을 붙이지 않는다.

[내용 규칙]
- 무엇에 관한 글인지 한눈에 알 수 있도록 핵심만 담는다.
- 구체적 날짜, 조항·고시·공고 번호, 기관 주소·부서명 나열은 넣지 않는다.
- 전체요약에 실제로 등장하는 핵심 키워드는 자연스럽게 포함한다(예: 홈쇼핑, 재승인, 재허가, 송출수수료, 유료방송, IPTV, 종합유선방송, 위성방송, 방송법, 시행령, 데이터방송채널, 일총량제, 중간광고, 가상광고, 간접광고, 시정명령, 의견청취 등 실제 등장한 단어만).
- 각 구간이 핵심 키워드를 담도록 하되 지나치게 축약하지 않고 적절한 정보량을 유지한다.
- 통계, 점수, 금액, 유효기간처럼 글의 핵심이 되는 숫자는 유지한다.

[통합·중복 규칙]
- 여러 첨부문서가 함께 들어오면 모두 하나로 통합해 단일 3줄 요약을 만든다. 문서별로 나누지 않는다.
- 비슷한 표현을 반복하지 않는다. 특히 의결, 보고, 승인 같은 의사결정 표현이 여러 번 겹치면 하나로 묶거나 다른 표현으로 분산한다.
- 글 제목에 이미 들어 있는 문구는 요약에서 반복하지 않는다.
- 회의록 글이면 처리된 핵심 안건 중심으로 요약한다. 단, 글 제목에 회차(예: 17차 회의)가 이미 있으므로 회차나 회의라는 표현은 반복하지 않는다.

[정확성 규칙]
- 본문에 없는 사실, 수치, 기관, 결과를 추측해서 추가하지 않는다. 주어진 내용만 사용한다.

[예시 1]
글 제목: (보도자료) 낡은 방송광고 규제 합리적으로 개선한다
출력: OTT 경쟁 대응 위해 낡은 방송광고 규제 합리적 개선, 방송법 시행령 개정 추진. 일총량제 1일 방송시간 20%로 확대, 중간광고 허용 프로그램 완화 및 횟수 확대. 가상·간접·자막광고 및 데이터방송채널 광고 크기 제한 1/3로 완화.

[예시 2]
글 제목: 방미통위 15차 회의
출력: 경남기업 DMB 소유제한 위반에 방송법 위반으로 관계기관 고발 의결. 케이티스카이라이프 위성방송 7년 재허가 및 OBS경인TV 역외 재송신 7년 승인. 2024년도 종편·보도PP 재승인조건 이행실적 점검 보고, MBN 미이행 접수 유보 및 권고사항 미이행 행정지도.

[입력]
글 제목: {title}
전체요약: {summary}

[출력]
"""

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


def _clean_feed(text):
    """피드 요약 응답을 정리한다.

    마크다운 제거 후 한 줄로 합치고, 마침표(.) 뒤에서 줄을 나눠
    한 블록 안에 줄바꿈(\\n)이 들어간 형태로 만든다 (블록은 1개, 화면엔 여러 줄).
    """
    if not text:
        return ""
    # 마크다운 기호 제거
    text = re.sub(r'[*_`#>]+', '', text)
    # 일단 한 줄로 합치기
    text = " ".join(ln.strip() for ln in text.splitlines() if ln.strip())
    text = re.sub(r'\s*[-•]\s*', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    # 길이 안전장치
    if len(text) > 300:
        text = text[:300].rstrip() + "."

    # 마침표(.) 기준으로 구간을 나눠 줄바꿈 삽입 (마침표는 유지)
    parts = [p.strip() for p in re.split(r'(?<=\.)\s+', text) if p.strip()]
    return "\n".join(parts)


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


def _make_feed_summary(item, full_summary):
    """전체요약을 받아 피드용 3줄 요약(마침표 뒤 줄바꿈 포함)을 생성한다.

    별도 Gemini 호출이 1회 추가된다. 한도 소진 시 빈 문자열을 반환한다.
    """
    if QUOTA_EXHAUSTED or not full_summary:
        return ""
    prompt = FEED_PROMPT_TEMPLATE.format(
        title=item.get('title', ''),
        summary=full_summary[:8000],
    )
    raw = _call_gemini(prompt)
    time.sleep(GEMINI_CALL_INTERVAL)
    if QUOTA_EXHAUSTED or not raw:
        return ""
    return _clean_feed(raw)


def summarize(item):
    """게시글의 요약문을 생성한다.

    전체 요약(첨부 통합 또는 본문)을 만든 뒤, 그 전체요약을 입력으로
    피드용 3줄 요약을 별도 호출로 생성해 item['feed_summary']에 저장한다.
    """
    item['summary_docs'] = []
    item['feed_summary'] = ""

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

    full_summary = None

    # --- 1순위: 첨부 문서 통합 요약 (게시글당 1회 호출) ---
    if target_docs:
        doc_names = " ".join(d['doc_name'] for d in target_docs)
        template = MEETING_PROMPT_TEMPLATE if _is_meeting_related(item, doc_names) else PROMPT_TEMPLATE

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
            full_summary = result

    # --- 2순위: 게시글 본문 요약 ---
    if not full_summary:
        content = (item.get('content') or '').strip()
        if content and not QUOTA_EXHAUSTED:
            template = MEETING_PROMPT_TEMPLATE if _is_meeting_related(item, "게시글 본문") else PROMPT_TEMPLATE
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
                full_summary = result

    # --- 전체요약 확보 시 피드용 3줄 요약 별도 생성 ---
    if full_summary:
        print("    -> Gemini 피드요약 요청")
        item['feed_summary'] = _make_feed_summary(item, full_summary)
        return full_summary

    # --- 3순위: 본문 앞부분 (기존 방식) ---
    print("    -> Gemini 요약 실패, 본문 앞부분으로 대체")
    content = (item.get('content') or '').strip()
    return content[:500] if content else "(내용 없음)"

# END OF FILE