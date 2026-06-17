from src.config import (
    HIGH_PRIORITY_KEYWORDS,
    INCLUDE_KEYWORDS,
    EXCLUDE_KEYWORDS,
    EXCLUDE_TITLE_KEYWORDS,
)


def check_keywords(item):
    """제목+본문에 수집 키워드가 포함되어 있는지 검사한다.

    - EXCLUDE_TITLE_KEYWORDS가 제목에 포함되면 무조건 제외 (무의미 공고 차단)
    - EXCLUDE_KEYWORDS가 제목+본문에 포함되면 제외
    - HIGH_PRIORITY_KEYWORDS 또는 INCLUDE_KEYWORDS가 하나라도 포함되면 수집
    - 일치 키워드 목록을 item['matched_keywords']에 저장
    """
    title = item.get('title', '')
    text = f"{title} {item.get('content', '')}".lower()

    for kw in EXCLUDE_TITLE_KEYWORDS:
        if kw in title:
            print(f"  -> 제외 (제목 필터 '{kw}'): {title[:20]}")
            return False

    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return False

    matched = []
    for kw in HIGH_PRIORITY_KEYWORDS + INCLUDE_KEYWORDS:
        if kw.lower() in text:
            matched.append(kw)

    if matched:
        item['matched_keywords'] = matched
        return True
    return False


def find_keywords_in_text(text):
    """주어진 텍스트(요약문 등)에서 수집 키워드를 찾아 목록으로 반환한다."""
    if not text:
        return []
    lowered = text.lower()
    found = []
    for kw in HIGH_PRIORITY_KEYWORDS + INCLUDE_KEYWORDS:
        if kw.lower() in lowered:
            found.append(kw)
    return found