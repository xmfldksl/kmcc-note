import re
from datetime import datetime, timedelta
from src.config import BOARDS, SEND_EMPTY_MAIL
from src.crawler import get_post_list, get_post_detail
from src.storage import load_seen, save_seen, get_hash
from src.filter import check_keywords
from src.summarizer import summarize
from src.mailer import send_mail
from src.notion_archiver import archive_to_notion


def main():
    seen_hashes = load_seen()
    new_seen_hashes = list(seen_hashes)
    matched_items = []

    kst_now = datetime.now() + timedelta(hours=9)
    today_str = kst_now.strftime('%Y-%m-%d')
    yesterday_str = (kst_now - timedelta(days=1)).strftime('%Y-%m-%d')

    print(f"KMCC 모니터링 시작 (기준 날짜: {yesterday_str} 이후)")

    for name, params in BOARDS.items():
        posts = get_post_list(name, params)
        for p in posts:
            detail_item = get_post_detail(p)
            post_date = detail_item.get('date', '1970-01-01')

            if post_date < yesterday_str:
                continue

            # --- 수집 대상 판정 ---
            is_mandatory_press = False
            if name == "보도자료" and re.search(r'\d{4}년 제\d+차 위원회', detail_item['title']):
                is_mandatory_press = True

            if not (name == "의사일정" or is_mandatory_press or check_keywords(detail_item)):
                continue

            # --- 의사일정 문서 종류 태그 ---
            doc_type = ""
            if name == "의사일정":
                att_names = " ".join(a['name'] for a in detail_item.get('attachments', []))
                if "속기록" in att_names:
                    doc_type = "[속기록] "
                elif "회의록" in att_names:
                    doc_type = "[회의록] "
                else:
                    doc_type = "[의사일정] "

            modified_title = f"{doc_type}{detail_item['title']}"
            detail_item['title'] = modified_title

            # --- 중복 검사 (요약 전에 수행: 중복이면 Gemini 호출 생략) ---
            p_hash = get_hash(name, modified_title, post_date, "v2")
            if p_hash in new_seen_hashes:
                print(f"  -> 중복 항목 건너뜀: {modified_title[:15]}")
                continue

            # --- 첨부파일 추출 + Gemini 요약 ---
            detail_item['summary'] = summarize(detail_item)

            matched_items.append(detail_item)
            new_seen_hashes.append(p_hash)
            print(f"  -> 신규 항목 수집: {modified_title[:15]}")

    # --- 출력 1: 메일 발송 ---
    if matched_items or SEND_EMPTY_MAIL:
        print(f"메일 발송 시도: 발견된 항목 {len(matched_items)}건")
        send_mail(matched_items, today_str)
    else:
        print(f"{yesterday_str} 이후 등록된 신규 항목이 없습니다.")

    # --- 출력 2: 노션 적재 (필터 통과 항목만) ---
    if matched_items:
        print(f"노션 적재 시도: {len(matched_items)}건")
        archive_to_notion(matched_items)

    save_seen(new_seen_hashes)


if __name__ == "__main__":
    main()