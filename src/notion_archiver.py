import os
import re
import time
import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"  # 단일 데이터 소스 DB는 이 버전으로 안정 동작
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 노션 무료 플랜 파일 업로드 한도(5MiB) 보호

OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# 노션 파일 업로드 API가 지원하는 확장자 (미지원 형식은 원본 링크로 대체)
SUPPORTED_UPLOAD_EXTS = {
    ".pdf", ".txt", ".json",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
}

# 회차 병합 대상 문서 종류 (의사일정 게시판 태그 + 보도자료 위원회결과)
MEETING_KINDS = ("속기록", "회의록", "의사일정")


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _split_text(text, size=1800):
    """노션 블록 글자 수 제한(2000자)에 맞춰 텍스트를 나눈다."""
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def _ensure_extension(filename, data):
    """파일명에 확장자가 없으면 내용 시그니처로 판별해 붙인다."""
    if os.path.splitext(filename)[1]:
        return filename
    if data[:5] == b"%PDF-":
        return filename + ".pdf"
    if data[:2] == b"PK":
        return filename + ".hwpx"
    if data[:8] == OLE_SIGNATURE:
        return filename + ".hwp"
    return filename + ".bin"


def _meeting_info(item):
    """회차 병합 대상인지 판별하고 (회차키, 중립 제목, 문서종류)를 반환한다.

    - 의사일정 게시판 글: 제목 태그([속기록]/[회의록]/[의사일정])가 문서종류
    - 보도자료의 'N차 위원회' 결과 글: 문서종류 '위원회결과'
    - 회차(연도+차수) 추출 실패 시 None (기존 방식으로 개별 적재)
    """
    board = item.get('board_name', '')
    title = item.get('title', '')

    kind = None
    if board == "의사일정":
        for k in MEETING_KINDS:
            if title.startswith(f"[{k}]"):
                kind = k
                break
        if kind is None:
            kind = "의사일정"
    elif board == "보도자료" and re.search(r'\d{4}년\s*제?\s*\d+\s*차\s*위원회', title):
        kind = "위원회결과"
    else:
        return None

    m = re.search(r'(\d{4})년\s*제?\s*(\d+)\s*차', title)
    if not m:
        m = re.search(r'제?\s*(\d{4})\s*-\s*(\d+)\s*차', title)
    if not m:
        return None

    year, session = m.group(1), int(m.group(2))
    session_key = f"{year}-{session}"
    neutral_title = f"{year}년 제{session}차 위원회"
    return session_key, neutral_title, kind


def _find_session_page(token, database_id, session_key):
    """'회차' 속성이 일치하는 기존 페이지를 조회한다. 없으면 None."""
    payload = {
        "filter": {"property": "회차", "rich_text": {"equals": session_key}},
        "page_size": 1,
    }
    try:
        resp = requests.post(
            f"{NOTION_API_BASE}/databases/{database_id}/query",
            headers=_headers(token), json=payload, timeout=60
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            return results[0] if results else None
        print(f"[Notion] 회차 조회 실패 (HTTP {resp.status_code}): {resp.text[:150]}")
    except Exception as e:
        print(f"[Notion] 회차 조회 에러: {e}")
    return None


def _page_keywords(page):
    """페이지 JSON에서 키워드 multi_select 이름 목록을 꺼낸다."""
    try:
        opts = page.get("properties", {}).get("키워드", {}).get("multi_select", [])
        return [o.get("name", "") for o in opts if o.get("name")]
    except Exception:
        return []


def _already_exists(token, database_id, item):
    """같은 제목+날짜의 페이지가 이미 있는지 데이터베이스에서 조회한다."""
    payload = {
        "filter": {"and": [
            {"property": "제목", "title": {"equals": item.get('title', '')[:200]}},
            {"property": "날짜", "date": {"equals": item.get('date', '1970-01-01')}},
        ]},
        "page_size": 1,
    }
    try:
        resp = requests.post(
            f"{NOTION_API_BASE}/databases/{database_id}/query",
            headers=_headers(token), json=payload, timeout=60
        )
        if resp.status_code == 200:
            return len(resp.json().get("results", [])) > 0
        print(f"[Notion] 중복 조회 실패 (HTTP {resp.status_code}), 적재는 계속 진행")
    except Exception as e:
        print(f"[Notion] 중복 조회 에러: {e}")
    return False


def _upload_file(token, filename, data):
    """노션 파일 업로드 API로 파일을 올리고 file_upload ID를 반환한다.

    미지원 확장자(hwp/hwpx 등)와 한도 초과 파일은 시도 없이 None을 반환해
    첨부파일 링크 표시로 대체되게 한다.
    """
    if not data:
        return None
    if len(data) > MAX_UPLOAD_BYTES:
        print(f"[Notion] 파일이 업로드 한도(5MiB) 초과, 링크로 대체: {filename[:30]}")
        return None
    filename = _ensure_extension(filename, data)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_UPLOAD_EXTS:
        print(f"[Notion] 노션 미지원 형식({ext}), 원본 링크로 대체: {filename[:30]}")
        return None
    try:
        resp = requests.post(
            f"{NOTION_API_BASE}/file_uploads",
            headers=_headers(token),
            json={"filename": filename[:900]},
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"[Notion] 업로드 생성 실패 (HTTP {resp.status_code}): {resp.text[:150]}")
            return None
        upload_info = resp.json()
        upload_id = upload_info["id"]
        # 노션이 등록한 형식을 그대로 사용 (불일치 방지)
        content_type = upload_info.get("content_type") or "application/octet-stream"

        send_headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
        }
        resp2 = requests.post(
            f"{NOTION_API_BASE}/file_uploads/{upload_id}/send",
            headers=send_headers,
            files={"file": (filename, data, content_type)},
            timeout=120,
        )
        if resp2.status_code == 200:
            print(f"[Notion] 파일 업로드 완료: {filename[:30]}")
            return upload_id
        print(f"[Notion] 파일 전송 실패 (HTTP {resp2.status_code}): {resp2.text[:150]}")
    except Exception as e:
        print(f"[Notion] 파일 업로드 에러: {e}")
    return None


def _summary_toggle(item, toggle_title):
    """전체 요약 토글 블록(접힌 상태)을 만든다."""
    summary_children = []
    for chunk in _split_text(item.get('summary', '')):
        summary_children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": chunk}}]}
        })
    return {
        "object": "block", "type": "toggle",
        "toggle": {
            "rich_text": [{"text": {"content": toggle_title}}],
            "children": summary_children,
        }
    }


def _attachment_blocks(uploaded, link_docs):
    """첨부파일(업로드분) + 첨부파일 링크(대체분) 블록 목록을 만든다."""
    blocks = []
    if uploaded:
        blocks.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "첨부파일"}}]}
        })
        for upload_id in uploaded:
            blocks.append({
                "object": "block", "type": "file",
                "file": {"type": "file_upload", "file_upload": {"id": upload_id}}
            })
    if link_docs:
        blocks.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "첨부파일 링크"}}]}
        })
        for doc in link_docs:
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{
                    "text": {
                        "content": doc['file_name'],
                        "link": {"url": doc['url']}
                    }
                }]}
            })
    return blocks


def _build_children(item, uploaded, link_docs, toggle_title="전체 요약"):
    """페이지 본문 블록: 피드요약(맨 위) + 전체 요약 토글 + 첨부 + 첨부파일 링크."""
    children = []

    # 1) 피드요약 (있을 때만, 소제목 없이 본문 맨 위)
    #    개행이 포함돼 있어도 한 블록 안에 넣어 블록이 나뉘지 않게 한다.
    feed_summary = item.get('feed_summary', '')
    if feed_summary:
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": feed_summary[:2000]}}]}
        })

    # 2) 전체 요약 토글 (접힌 상태로 생성)
    children.append(_summary_toggle(item, toggle_title))

    # 3) 첨부파일 + 첨부파일 링크
    children.extend(_attachment_blocks(uploaded, link_docs))

    return children


def _build_append_section(item, uploaded, link_docs, kind):
    """기존 회차 페이지 하단에 덧붙일 섹션 블록: 구분선 + 토글 + 원문 + 첨부."""
    blocks = [{"object": "block", "type": "divider", "divider": {}}]
    blocks.append(_summary_toggle(item, f"[{kind}] 전체 요약"))
    url = item.get('url')
    if url:
        blocks.append({
            "object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{
                "text": {"content": f"{kind} 원문 보기", "link": {"url": url}}
            }]}
        })
    blocks.extend(_attachment_blocks(uploaded, link_docs))
    return blocks


def _upload_item_files(token, item):
    """항목의 첨부 문서들을 업로드하고 (업로드 ID 목록, 링크 대체 목록)을 반환한다."""
    uploaded = []
    link_docs = []
    for doc in item.get('summary_docs', []):
        upload_id = _upload_file(token, doc['file_name'], doc.get('data'))
        if upload_id:
            uploaded.append(upload_id)
        else:
            link_docs.append(doc)
        time.sleep(0.5)
    return uploaded, link_docs


def _set_self_link(token, page):
    """'요약보기' 속성에 페이지 자신의 주소를 기록한다."""
    page_id = page.get("id")
    page_url = page.get("url")
    if not (page_id and page_url):
        return
    resp = requests.patch(
        f"{NOTION_API_BASE}/pages/{page_id}",
        headers=_headers(token),
        json={"properties": {"요약보기": {"url": page_url}}},
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"[Notion] 요약보기 링크 기록 실패 (HTTP {resp.status_code}): "
              f"노션 표에 '요약보기' URL 속성이 있는지 확인 필요")


def _archive_meeting_item(token, database_id, item, session_key, neutral_title, kind):
    """회차 병합 적재: 같은 회차 페이지가 있으면 덧붙이고, 없으면 중립 제목으로 생성."""
    page = _find_session_page(token, database_id, session_key)

    if page is not None:
        # --- 같은 문서종류가 이미 들어갔으면 건너뜀 (키워드로 판별) ---
        existing_keywords = _page_keywords(page)
        if kind in existing_keywords:
            print(f"[Notion] 회차 {session_key}에 '{kind}' 이미 존재, 건너뜀")
            return

        uploaded, link_docs = _upload_item_files(token, item)

        # --- 페이지 하단에 섹션 덧붙이기 ---
        page_id = page.get("id")
        resp = requests.patch(
            f"{NOTION_API_BASE}/blocks/{page_id}/children",
            headers=_headers(token),
            json={"children": _build_append_section(item, uploaded, link_docs, kind)},
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"[Notion] 회차 병합 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
            return

        # --- 키워드 속성에 문서종류·필터 키워드 합치기 ---
        merged = list(existing_keywords)
        for kw in [kind] + item.get('matched_keywords', []):
            if kw and kw not in merged:
                merged.append(kw)
        requests.patch(
            f"{NOTION_API_BASE}/pages/{page_id}",
            headers=_headers(token),
            json={"properties": {"키워드": {"multi_select": [{"name": k} for k in merged]}}},
            timeout=60,
        )
        print(f"[Notion] 회차 {session_key} 페이지에 '{kind}' 병합 완료")
        return

    # --- 회차 페이지가 없으면 중립 제목으로 새로 생성 ---
    uploaded, link_docs = _upload_item_files(token, item)

    keywords = []
    for kw in [kind] + item.get('matched_keywords', []):
        if kw and kw not in keywords:
            keywords.append(kw)

    properties = {
        "게시판": {"select": {"name": "의사일정"}},
        "제목": {"title": [{"text": {"content": neutral_title[:200]}}]},
        "날짜": {"date": {"start": item.get('date', '1970-01-01')}},
        "원문보기": {"url": item.get('url') or None},
        "회차": {"rich_text": [{"text": {"content": session_key}}]},
        "키워드": {"multi_select": [{"name": k} for k in keywords]},
    }

    payload = {
        "parent": {"database_id": database_id},
        "properties": properties,
        "children": _build_children(item, uploaded, link_docs,
                                    toggle_title=f"[{kind}] 전체 요약"),
    }
    resp = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(token), json=payload, timeout=60
    )
    if resp.status_code != 200:
        print(f"[Notion] 회차 페이지 생성 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
        return

    print(f"[Notion] 회차 {session_key} 페이지 생성 완료 ({kind})")
    _set_self_link(token, resp.json())


def archive_to_notion(items):
    """필터를 통과한 수집 항목들을 노션 데이터베이스에 적재한다.

    - 의사일정 3종(의사일정/회의록/속기록)과 보도자료 위원회결과는
      '회차' 속성 기준으로 한 페이지에 병합 (게시판은 '의사일정'으로 통일,
      제목은 'YYYY년 제N차 위원회' 중립 제목)
    - 그 외 글은 기존 방식: 제목+날짜 중복 조회 후 개별 페이지 생성
    - 본문: 피드요약(맨 위) + 전체 요약 토글 + 첨부/첨부파일 링크
    - 미지원 형식(hwp/hwpx/md 등)·업로드 실패 문서는 첨부파일 링크로 표시
    - 노션 장애가 메일 발송을 막지 않도록 실패 시 로그만 남긴다
    """
    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not token or not database_id:
        print("[Notion] 토큰 또는 DB ID 미설정, 적재 건너뜀")
        return

    for item in items:
        try:
            # --- 회차 병합 대상 판별 ---
            meeting = _meeting_info(item)
            if meeting is not None:
                session_key, neutral_title, kind = meeting
                _archive_meeting_item(token, database_id, item,
                                      session_key, neutral_title, kind)
                time.sleep(0.5)
                continue

            # --- 일반 글: 기존 방식 ---
            if _already_exists(token, database_id, item):
                print(f"[Notion] 이미 존재하여 건너뜀: {item.get('title', '')[:20]}")
                continue

            uploaded, link_docs = _upload_item_files(token, item)

            properties = {
                "게시판": {"select": {"name": item.get('board_name', '기타')}},
                "제목": {"title": [{"text": {"content": item.get('title', '')[:200]}}]},
                "날짜": {"date": {"start": item.get('date', '1970-01-01')}},
                "원문보기": {"url": item.get('url') or None},
            }
            keywords = item.get('matched_keywords', [])
            if keywords:
                properties["키워드"] = {
                    "multi_select": [{"name": kw} for kw in keywords]
                }

            payload = {
                "parent": {"database_id": database_id},
                "properties": properties,
                "children": _build_children(item, uploaded, link_docs),
            }

            resp = requests.post(
                f"{NOTION_API_BASE}/pages",
                headers=_headers(token), json=payload, timeout=60
            )
            if resp.status_code != 200:
                print(f"[Notion] 적재 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
                continue

            print(f"[Notion] 적재 완료: {item.get('title', '')[:20]}")
            _set_self_link(token, resp.json())
        except Exception as e:
            print(f"[Notion] 호출 에러: {e}")
        time.sleep(0.5)  # 노션 API 초당 요청 제한(평균 3회) 보호


# END OF FILE