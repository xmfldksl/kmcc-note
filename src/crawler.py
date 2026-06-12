from bs4 import BeautifulSoup
import time
import random
import urllib.parse
from curl_cffi import requests
from src.config import RSS_BASE_URL
import urllib3
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

PROXY = None
REQUEST_TIMEOUT = 60  # 응답 대기시간(초)
MAX_BACKFILL_PAGES = 50  # 백필 시 게시판당 최대 페이지 수 (안전 상한)

# 이번 실행에서 목록 수집이 최종 실패(연결 오류)한 게시판 이름 목록
FAILED_BOARDS = []


def _extract_row_date(cols):
    """목록 행의 셀들에서 YYYY-MM-DD 형식의 등록일을 찾는다."""
    for td in cols:
        txt = td.get_text(strip=True)
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', txt):
            return txt
    return None


def _extract_row_attachments(row):
    """목록 행에서 첨부파일 링크를 수집한다 (파일명은 아이콘 img의 alt)."""
    files = []
    seen_urls = set()
    for a in row.select('a[href*="download.do"]'):
        href = a.get('href', '')
        if not href:
            continue
        url = urllib.parse.urljoin(RSS_BASE_URL, href)
        if url in seen_urls:
            continue
        img = a.select_one('img')
        name = img.get('alt', '').strip() if img else a.get_text(strip=True)
        if not name:
            continue
        seen_urls.add(url)
        files.append({'name': name, 'url': url})
    return files


def _fetch_soup(url, board_name):
    """목록 페이지를 재시도 포함하여 가져온다. 최종 실패 시 None."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(random.uniform(4.0, 8.0))
            response = requests.get(
                url,
                impersonate="chrome116",
                headers=DEFAULT_HEADERS,
                proxies=PROXY,
                timeout=REQUEST_TIMEOUT,
                verify=False
            )
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"[{board_name}] 목록 수집 에러 (시도 {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                return None
            time.sleep(5.0)


def _parse_rows(board_name, rows, page_url):
    """목록 페이지의 행들을 게시글 딕셔너리 목록으로 변환한다."""
    posts = []
    for row in rows:
        cols = row.select('td')

        # 심결정보 게시판 특수 처리 (번호, 안건번호, 제목, 첨부파일, 공공누리, 작성일 순)
        if board_name == "심결정보" and len(cols) >= 6:
            title = cols[2].get_text(strip=True)  # 제목 열
            date_val = cols[5].get_text(strip=True)  # 작성일 열

            posts.append({
                'board_name': board_name, 'title': title, 'url': page_url,
                'content': f"안건번호: {cols[1].get_text(strip=True)}",
                'attachments': _extract_row_attachments(row),
                'date': date_val, 'is_direct': True
            })
        else:
            # 일반 게시판 처리: 목록에서 날짜와 첨부파일까지 수집
            a_tag = row.select_one('a[href*="boardSeq"]') or row.select_one('a')
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            href = a_tag.get('href', '')
            link = urllib.parse.urljoin(RSS_BASE_URL, href)

            posts.append({
                'board_name': board_name, 'title': title, 'url': link,
                'content': "",
                'attachments': _extract_row_attachments(row),
                'date': _extract_row_date(cols),
                'is_direct': False
            })
    return posts


def get_post_list(board_name, params, from_date=None):
    """게시판 목록을 수집한다.

    from_date(YYYY-MM-DD)가 주어지면 해당 날짜 이전 글이 나올 때까지
    다음 페이지(cp=2, 3, ...)를 계속 넘기며 수집한다 (백필 모드).
    from_date가 없으면 기존처럼 1페이지만 수집한다.
    """
    base_url = params['url']
    sep = '&' if '?' in base_url else '?'
    max_pages = MAX_BACKFILL_PAGES if from_date else 1

    all_posts = []
    seen_keys = set()

    for cp in range(1, max_pages + 1):
        page_url = f"{base_url}{sep}cp={cp}"
        soup = _fetch_soup(page_url, board_name)
        if soup is None:
            FAILED_BOARDS.append(board_name)
            break

        rows = soup.select('table tbody tr')
        if not rows:
            if cp == 1:
                print(f"[{board_name}] 게시글 없음 또는 목록 추출 실패")
            break

        page_posts = _parse_rows(board_name, rows, page_url)

        # 페이지 간 중복 제거 (제목+날짜+링크 기준)
        new_posts = []
        for p in page_posts:
            key = f"{p['title']}|{p.get('date')}|{p['url']}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            new_posts.append(p)

        if not new_posts:
            break  # 마지막 페이지를 넘어 같은 내용이 반복되는 경우 종료

        all_posts.extend(new_posts)

        if from_date:
            print(f"[{board_name}] {cp}페이지: {len(new_posts)}건 수집")
            dates = [p['date'] for p in new_posts if p.get('date')]
            # 이 페이지에 기준 날짜보다 오래된 글이 있으면 더 넘길 필요 없음
            if dates and min(dates) < from_date:
                break

    print(f"[{board_name}] {len(all_posts)}개 항목 수집 완료")
    return all_posts


def get_post_detail(item):
    # 목록에서 날짜와 제목을 이미 확정한 경우(심결정보 등) 상세 페이지 접속 생략
    if item.get('is_direct'):
        print(f"  -> [{item['board_name']}] 목록 데이터 사용 (날짜: {item['date']}): {item['title'][:15]}")
        return item

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(random.uniform(5.0, 10.0))
            response = requests.get(
                item['url'],
                impersonate="chrome116",
                headers=DEFAULT_HEADERS,
                proxies=PROXY,
                timeout=REQUEST_TIMEOUT,
                verify=False
            )
            soup = BeautifulSoup(response.content, 'html.parser')

            content_area = soup.select_one('.view_con') or soup.select_one('#contents') or soup.select_one('.board_view')
            raw_text = content_area.get_text(strip=True) if content_area else soup.get_text(strip=True)

            content_after_title = raw_text.split("제목", 1)[1] if "제목" in raw_text else raw_text

            date_match = re.search(r'(등록일|작성일).*?(\d{4}-\d{2}-\d{2})', content_after_title)
            if date_match:
                item['date'] = date_match.group(2)
            elif not item.get('date'):
                backup_match = re.search(r'(\d{4}-\d{2}-\d{2})', raw_text)
                item['date'] = backup_match.group(1) if backup_match else "1970-01-01"

            item['content'] = content_after_title.strip()

            # 첨부파일: 상세 페이지에서 더 정확한 파일명(span.font_56)으로 수집되면 교체
            files = []
            seen_urls = set()
            for a in soup.select('a[href*="download.do"]'):
                href = a.get('href', '')
                if not href:
                    continue
                url = urllib.parse.urljoin(RSS_BASE_URL, href)
                if url in seen_urls:
                    continue
                span = a.select_one('span.font_56')
                name = span.get_text(strip=True) if span else a.get_text(strip=True)
                if not name or name in ("다운로드", "뷰어보기"):
                    continue
                seen_urls.add(url)
                files.append({'name': name, 'url': url})
            if files:
                item['attachments'] = files

            print(f"  -> 상세 데이터 수집 완료 (날짜: {item['date']}, 첨부 {len(item['attachments'])}개): {item['title'][:15]}")
            return item
        except Exception as e:
            print(f"  -> 상세 페이지 접속 에러 (시도 {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                if not item.get('date'):
                    item['date'] = "1970-01-01"
                return item
            time.sleep(5.0)

# END OF FILE