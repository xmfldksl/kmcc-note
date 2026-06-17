"""노션에 이미 적재된 페이지의 키워드를 제목+요약 기준으로 재계산해 갱신한다.

- 사이트 재크롤링/Gemini 재요약 없음 (API 한도 소모 없음)
- 기존 키워드 유지 + 제목·요약에서 찾은 키워드 추가 (합치기)
- 페이지 본문의 '요약' 텍스트를 읽어 키워드를 다시 찾음
실행: python -m retag_notion  (로컬, 환경변수 NOTION_TOKEN/NOTION_DATABASE_ID 필요)
"""
import os
import time
import requests
from src.filter import find_keywords_in_text

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _get_all_pages(token, database_id):
    """데이터베이스의 모든 페이지를 페이지네이션으로 조회한다."""
    pages = []
    cursor = None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        resp = requests.post(
            f"{NOTION_API_BASE}/databases/{database_id}/query",
            headers=_headers(token), json=payload, timeout=60
        )
        if resp.status_code != 200:
            print(f"[조회 실패] HTTP {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.4)
    return pages


def _get_page_text(token, page_id):
    """페이지 본문 블록의 텍스트를 모두 모아 반환한다 (요약 포함)."""
    texts = []
    cursor = None
    while True:
        url = f"{NOTION_API_BASE}/blocks/{page_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        resp = requests.get(url, headers=_headers(token), timeout=60)
        if resp.status_code != 200:
            break
        data = resp.json()
        for block in data.get("results", []):
            btype = block.get("type", "")
            content = block.get(btype, {})
            rich = content.get("rich_text", [])
            for r in rich:
                t = r.get("plain_text", "")
                if t:
                    texts.append(t)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.3)
    return "\n".join(texts)


def _get_title(page):
    """페이지의 제목 속성 텍스트를 반환한다."""
    props = page.get("properties", {})
    title_prop = props.get("제목", {})
    parts = title_prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts)


def _get_existing_keywords(page):
    """페이지의 기존 키워드(다중 선택) 목록을 반환한다."""
    props = page.get("properties", {})
    kw_prop = props.get("키워드", {})
    return [opt.get("name", "") for opt in kw_prop.get("multi_select", [])]


def retag():
    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not token or not database_id:
        print("NOTION_TOKEN 또는 NOTION_DATABASE_ID 미설정")
        return

    pages = _get_all_pages(token, database_id)
    print(f"총 {len(pages)}개 페이지 조회됨")

    updated = 0
    for page in pages:
        page_id = page["id"]
        title = _get_title(page)
        existing = _get_existing_keywords(page)

        body_text = _get_page_text(token, page_id)
        time.sleep(0.3)

        # 제목 + 본문(요약)에서 키워드 재계산
        found = find_keywords_in_text(f"{title}\n{body_text}")

        # 기존 키워드 유지 + 새로 찾은 키워드 합치기 (중복 제거, 순서 유지)
        merged = list(existing)
        for kw in found:
            if kw not in merged:
                merged.append(kw)

        # 변화가 없으면 갱신 생략
        if set(merged) == set(existing):
            continue

        resp = requests.patch(
            f"{NOTION_API_BASE}/pages/{page_id}",
            headers=_headers(token),
            json={"properties": {"키워드": {"multi_select": [{"name": k} for k in merged]}}},
            timeout=60,
        )
        if resp.status_code == 200:
            updated += 1
            added = [k for k in merged if k not in existing]
            print(f"[갱신] {title[:25]} | 추가: {', '.join(added)}")
        else:
            print(f"[갱신 실패] {title[:25]} | HTTP {resp.status_code}: {resp.text[:150]}")
        time.sleep(0.4)

    print(f"\n완료: {updated}개 페이지 키워드 갱신")


if __name__ == "__main__":
    retag()

# END OF FILE