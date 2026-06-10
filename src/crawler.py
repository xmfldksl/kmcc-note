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


def get_post_list(board_name, params):
    target_url = params['url']
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(random.uniform(4.0, 8.0))
            response = requests.get(
                target_url,
                impersonate="chrome116",
                headers=DEFAULT_HEADERS,
                proxies=PROXY,
                timeout=30,
                verify=False
            )

            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.select('table tbody tr')

            if not rows:
                print(f"[{board_name}] 게시글 목록 추출 실패")
                return []

            posts = []
            for row in rows:
                cols = row.select('td')

                # 심결정보 게시판 특수 처리 (번호, 안건번호, 제목, 첨부파일, 공공누리, 작성일 순)
                if board_name == "심결정보" and len(cols) >= 6:
                    title = cols[2].get_text(strip=True)  # 제목 열
                    date_val = cols[5].get_text(strip=True)  # 작성일 열
                    link = target_url  # 상세 페이지가 없으므로 목록 주소 유지

                    posts.append({
                        'board_name': board_name, 'title': title, 'url': link,
                        'content': f"안건번호: {cols[1].get_text(strip=True)}",
                        'attachments': [], 'date': date_val, 'is_direct': True
                    })
                else:
                    # 일반 게시판 처리
                    a_tag = row.select_one('a')
                    if not a_tag:
                        continue

                    title = a_tag.get_text(strip=True)
                    href = a_tag.get('href', '')
                    link = urllib.parse.urljoin(RSS_BASE_URL, href)

                    posts.append({
                        'board_name': board_name, 'title': title, 'url': link,
                        'content': "", 'attachments': [], 'date': None, 'is_direct': False
                    })

            print(f"[{board_name}] {len(posts)}개 항목 수집 완료")
            return posts
        except Exception as e:
            print(f"[{board_name}] 목록 수집 에러 (시도 {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                return []
            time.sleep(5.0)


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
                timeout=30,
                verify=False
            )
            soup = BeautifulSoup(response.text, 'html.parser')

            content_area = soup.select_one('.view_con') or soup.select_one('#contents') or soup.select_one('.board_view')
            raw_text = content_area.get_text(strip=True) if content_area else soup.get_text(strip=True)

            content_after_title = raw_text.split("제목", 1)[1] if "제목" in raw_text else raw_text

            date_match = re.search(r'(등록일|작성일).*?(\d{4}-\d{2}-\d{2})', content_after_title)
            if date_match:
                item['date'] = date_match.group(2)
            else:
                backup_match = re.search(r'(\d{4}-\d{2}-\d{2})', raw_text)
                item['date'] = backup_match.group(1) if backup_match else "1970-01-01"

            item['content'] = content_after_title.strip()

            # 첨부파일: 파일명 + 다운로드 링크(href)를 함께 수집 (변경 지점)
            files = []
            for f in soup.select('.fileList a'):
                href = f.get('href', '')
                if not href:
                    continue
                files.append({
                    'name': f.get_text(strip=True),
                    'url': urllib.parse.urljoin(RSS_BASE_URL, href)
                })
            item['attachments'] = files

            print(f"  -> 상세 데이터 수집 완료 (날짜: {item['date']}, 첨부 {len(files)}개): {item['title'][:15]}")
            return item
        except Excepti