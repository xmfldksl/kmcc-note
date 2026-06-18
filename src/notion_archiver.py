import os
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


def _build_children(item, uploaded, link_docs):
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

    # 2) 전체 요약 토글 (피드요약 유무와 무관하게 항상 표시, 접힌 상태로 생성)
    summary_children = []
    for chunk in _split_text(item.get('summary', '')):
        summary_children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": chunk}}]}
        })
    children.append({
        "object": "block", "type": "toggle",
        "toggle": {
            "rich_text": [{"text": {"content": "전체 요약"}}],
            "children": summary_children,
        }
    })

    # 3) 업로드된 첨부파일
    if uploaded:
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "첨부파일"}}]}
        })
        for upload_id in uploaded:
            children.append({
                "object": "block", "type": "file",
                "file": {"type": "file_upload", "file_upload": {"id": upload_id}}
            })

    # 4) 업로드하지 못한 문서만 첨부파일 링크로 표시
    if link_docs:
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "첨부파일 링크"}}]}
        })
        for doc in link_docs:
            children.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{
                    "text": {
                        "content": doc['file_name'],
                        "link": {"url": doc['url']}
                    }
                }]}
            })

    return children


def archive_to_notion(items):
    """필터를 통과한 수집 항목들을 노션 데이터베이스에 적재한다.

    - 적재 전 제목+날짜 기준으로 중복 조회 후 건너뜀
    - 본문: 피드요약(맨 위) + 전체 요약 토글 + 첨부/첨부파일 링크
    - 첨부 문서 파일을 페이지 본문에 직접 업로드 (지원 형식, 5MiB 이하)
    - 미지원 형식(hwp/hwpx 등)·업로드 실패 문서는 첨부파일 링크로 표시
    - 생성된 페이지의 노션 주소를 '요약보기' 속성에 기록
    - 노션 장애가 메일 발송을 막지 않도록 실패 시 로그만 남긴다
    """
    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not token or not database_id:
        print("[Notion] 토큰 또는 DB ID 미설정, 적재 건너뜀")
        return

    for item in items:
        try:
            # --- 중복 체크 ---
            if _already_exists(token, database_id, item):
                print(f"[Notion] 이미 존재하여 건너뜀: {item.get('title', '')[:20]}")
                continue

            # --- 첨부파일 업로드 (미지원/실패분은 링크 표시 대상으로 분류) ---
            uploaded = []
            link_docs = []
            for doc in item.get('summary_docs', []):
                upload_id = _upload_file(token, doc['file_name'], doc.get('data'))
                if upload_id:
                    uploaded.append(upload_id)
                else:
                    link_docs.append(doc)
                time.sleep(0.5)

            # --- 페이지 생성 ---
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

            page = resp.json()
            print(f"[Notion] 적재 완료: {item.get('title', '')[:20]}")

            # --- '요약보기' 속성에 페이지 자신의 주소 기록 ---
            page_id = page.get("id")
            page_url = page.get("url")
            if page_id and page_url:
                resp2 = requests.patch(
                    f"{NOTION_API_BASE}/pages/{page_id}",
                    headers=_headers(token),
                    json={"properties": {"요약보기": {"url": page_url}}},
                    timeout=60,
                )
                if resp2.status_code != 200:
                    print(f"[Notion] 요약보기 링크 기록 실패 (HTTP {resp2.status_code}): "
                          f"노션 표에 '요약보기' URL 속성이 있는지 확인 필요")
        except Exception as e:
            print(f"[Notion] 호출 에러: {e}")
        time.sleep(0.5)  # 노션 API 초당 요청 제한(평균 3회) 보호


# END OF FILE