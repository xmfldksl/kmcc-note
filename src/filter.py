from src.config import HIGH_PRIORITY_KEYWORDS, INCLUDE_KEYWORDS, EXCLUDE_KEYWORDS


def check_keywords(item):
    """제목+본문에 수집 키워드가 포함되어 있는지 검사한다.

    - EXCLUDE_KEYWORDS가 포함되면 무조건 제외
    - HIGH_PRIORITY_KEYWORDS 또는 INCLUDE_KEYWORDS가 하나라도 포함되면 수집
    - 일치 키워드 목록을 item['matched_keywords']에 저장
    """
    text = f"{item.get('title', '')} {item.get('content', '')}".lower()

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