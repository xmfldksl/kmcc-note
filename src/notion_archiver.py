import os
import time
import requests

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"  # 단일 데이터 소스 DB는 이 버전으로 안정 동작


def _split_text(text, size=1800):
    """노션 블록 글자 수 제한(2000자)에 맞춰 텍스트를 나눈다."""
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def _build_children(item):
    """페이지 본문 블록: 요약 전체 + 원본 문서 링크 목록."""
    children = []

    # 요약 본문
    children.append({
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [{"text": {"content": "요약"}}]}
    })
    for chunk in _split_text(item.get('summary', '')):
        children.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": chunk}}]}
        })

    # 원본 문서 링크
    docs = item.get('summary_docs', [])
    if docs:
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": "원본 문서"}}]}
        })
        for doc in docs:
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

    노션 장애가 메일 발송을 막지 않도록 실패 시 로그만 남긴다.
    속성 구성: 게시판(선택) / 제목(타이틀) / 날짜 / 키워드(다중선택) / 링크(URL)
    """
    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not token or not database_id:
        print("[Notion] 토큰 또는 DB ID 미설정, 적재 건너뜀")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    for item in items:
        properties = {
            "게시판": {"select": {"name": item.get('board_name', '기타')}},
            "제목": {"title": [{"text": {"content": item.get('title', '')[:200]}}]},
            "날짜": {"date": {"start": item.get('date', '1970-01-01')}},
            "링크": {"url": item.get('url') or None},
        }
        keywords = item.get('matched_keywords', [])
        if keywords:
            properties["키워드"] = {
                "multi_select": [{"name": kw} for kw in keywords]
            }

        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": _build_children(item),
        }

        try:
            resp = requests.post(NOTION_API_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                print(f"[Notion] 적재 완료: {item.get('title', '')[:20]}")
            else:
                print(f"[Notion] 적재 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"[Notion] 호출 에러: {e}")
        time.sleep(0.5)  # 노션 API 초당 요청 제한(평균 3회) 보호