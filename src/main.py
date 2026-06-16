import os
import re
from datetime import datetime, timedelta
from src.config import BOARDS, SEND_EMPTY_MAIL, TEST_BOARDS, BACKFILL_FROM
from src.crawler import get_post_list, get_post_detail, FAILED_BOARDS
from src.storage import load_seen, save_seen, get_hash
from src.filter import check_keywords
from src import summarizer
from src.mailer import send_mail
from src.notion_archiver import archive_to_notion


def _meeting_doc_type(att_names):
    if "속기록" in att_names:
        return "[속기록] "
    if "회의록" in att_names:
        return "[회의록] "
    return "[의사일정] "


def main():
    seen_hashes = load_seen()
    new_seen_hashes = list(seen_hashes)
    seen_set = set(seen_hashes)
    matched_items = []
    quota_stop = False

    kst_now = datetime.now() + timedelta(hours=9)
    today_str = kst_now.strftime('%Y-%m-%d')
    yesterday_str = (kst_now - timedelta(days=1)).strftime('%Y-%m-%d')

    # --- 기준 날짜: 백필 모드면 지정 날짜, 아니면 어제 ---
    if BACKFILL_FROM and re.fullmatch(r'\d{4}-\d{2}-\d{2}', BACKFILL_FROM):
        base_date = BACKFILL_FROM
        from_date = BACKFILL_FROM
        print(f"백필 모드: {base_date} 이후 글을 페이지 넘김으로 수집")
    else:
        base_date = yesterday_str
        from_date = None

    # --- 테스트 모드: 지정된 게시판만 실행 ---
    boards = BOARDS
    if TEST_BOARDS:
        names = [n.strip() for n in TEST_BOARDS.split(",") if n.strip()]
        boards = {k: v for k, v in BOARDS.items() if k in names}
        print(f"테스트 모드: {list(boards.keys())}만 실행")

    print(f"KMCC 모니터링 시작 (기준 날짜: {base_date} 이후)")

    for name, params in boards.items():
        if quota_stop:
            break
        posts = get_post_list(name, params, from_date=from_date)
        for p in posts:
            # --- 1차 필터: 목록의 등록일이 기준보다 오래되면 건너뜀 ---
            list_date = p.get('date')
            if list_date and list_date < base_date:
                continue

            # --- 사전 중복 검사: 목록 정보만으로 해시를 만들어 이미 처리된 글이면
            #     상세 페이지 접속 자체를 생략 (재실행 시 접속량 최소화) ---
            list_title = p.get('title', '')
            if list_date and name != "심결정보":
                if name == "의사일정":
                    att_names = " ".join(a['name'] for a in p.get('attachments', []))
                    pre_title = f"{_meeting_doc_type(att_names)}{list_title}"
                else:
                    pre_title = list_title
                pre_hash = get_hash(name, pre_title, list_date, "v2")
                if pre_hash in seen_set:
                    continue

            detail_item = get_post_detail(p)
            post_date = detail_item.get('date', '1970-01-01')

            if post_date < base_date:
                continue

            # --- 수집 대상 판정 ---
            is_mandatory_press = False
            if name == "보도자료" and re.search(r'\d{4}년 제\d+차 위원회', detail_item['title']):
                is_mandatory_press = True

            if not (name == "의사일정" or is_mandatory_press or check_keywords(detail_item)):
                continue

            # --- 의사일정 문서 종류 태그 + 키워드 기록 ---
            doc_type = ""
            if name == "의사일정":
                att_names = " ".join(a['name'] for a in detail_item.get('attachments', []))
                doc_kinds = [k for k in ("의사일정", "회의록", "속기록") if k in att_names]
                if not doc_kinds:
                    doc_kinds = ["의사일정"]
                detail_item['matched_keywords'] = doc_kinds
                doc_type = _meeting_doc_type(att_names)

            modified_title = f"{doc_type}{detail_item['title']}"
            detail_item['title'] = modified_title

            # --- 중복 검사 (상세 단계 최종 확인) ---
            p_hash = get_hash(name, modified_title, post_date, "v2")
            if p_hash in seen_set:
                print(f"  -> 중복 항목 건너뜀: {modified_title[:15]}")
                continue

            # --- 첨부파일 추출 + Gemini 요약 ---
            summary = summarizer.summarize(detail_item)

            # --- 일일 한도 소진: 이 항목은 기록하지 않고 전체 중단 (다음 실행에서 이어짐) ---
            if summarizer.QUOTA_EXHAUSTED:
                print(f"Gemini 일일 한도 소진 — 실행을 중단합니다. "
                      f"'{modified_title[:20]}'부터는 다음 실행에서 이어서 처리됩니다.")
                quota_stop = True
                break

            detail_item['summary'] = summary
            matched_items.append(detail_item)
            new_seen_hashes.append(p_hash)
            seen_set.add(p_hash)
            print(f"  -> 신규 항목 수집: {modified_title[:15]}")

    # --- 출력 1: 메일 발송 (SKIP_MAIL=1이면 생략, 실패해도 노션 적재는 계속) ---
    if os.getenv("SKIP_MAIL", "").strip() == "1":
        print("메일 발송 생략 (SKIP_MAIL=1)")
    elif matched_items or SEND_EMPTY_MAIL:
        print(f"메일 발송 시도: 발견된 항목 {len(matched_items)}건")
        try:
            send_mail(matched_items, today_str, failed_boards=FAILED_BOARDS)
        except Exception as e:
            print(f"메일 발송 실패 (노션 적재는 계속 진행): {e}")
    else:
        print(f"{base_date} 이후 등록된 신규 항목이 없습니다.")

    # --- 출력 2: 노션 적재 (필터 통과 항목만) ---
    if matched_items:
        print(f"노션 적재 시도: {len(matched_items)}건")
        archive_to_notion(matched_items)

    save_seen(new_seen_hashes)

    if quota_stop:
        print("안내: Gemini 일일 한도가 초기화된 뒤 같은 설정으로 재실행하면 "
              "중단 지점부터 이어서 수집됩니다.")


if __name__ == "__main__":
    main()

# END OF FILE