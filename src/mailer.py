import smtplib
import html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.config import (
    SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_APP_PASSWORD, MAIL_TO,
    NOTION_PAGE_URL,
)

# 메일 전체 공통 폰트 (맑은 고딕, 10pt, 검정)
BASE_FONT = "font-family:'Malgun Gothic',sans-serif;font-size:10pt;color:#000000"


def _build_item_html(item):
    title = html.escape(item.get('title', ''))
    board = html.escape(item.get('board_name', ''))
    date = html.escape(item.get('date', ''))
    url = item.get('url', '')
    keywords = ", ".join(item.get('matched_keywords', []))
    summary = html.escape(item.get('summary', '')).replace("\n", "<br>")

    doc_links = ""
    for doc in item.get('summary_docs', []):
        doc_links += (
            f'<li><a href="{doc["url"]}">{html.escape(doc["file_name"])}</a></li>'
        )
    if doc_links:
        doc_links = f"<p style='margin:4px 0'>첨부파일 링크 :</p><ul>{doc_links}</ul>"

    kw_line = f"<p style='margin:4px 0'>연관 키워드 : {keywords}</p>" if keywords else ""

    return f"""
    <div style="border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:14px">
      <p style="margin:0 0 6px 0">
        <span style="font-weight:bold">{board}</span>
        <span style="font-weight:bold">{date}</span>
      </p>
      <p style="margin:0 0 8px 0"><b><a href="{url}">{title}</a></b></p>
      {kw_line}
      <div style="padding:10px 0;line-height:1.6">
        {summary}
      </div>
      {doc_links}
    </div>
    """


def send_mail(items, today_str, failed_boards=None):
    """수집 결과를 HTML 메일로 발송한다.

    - 상단: 노션 안내 (NOTION_PAGE_URL 설정 시)
    - 하단: 최종 수집 실패 게시판 표시
    - 배경색 미사용, 맑은 고딕 10pt 검정으로 통일
    """
    if items:
        subject = f"[방미통위] {today_str} 신규 {len(items)}건"
        body_items = "".join(_build_item_html(i) for i in items)
    else:
        subject = f"[방미통위] {today_str} 신규 항목 없음"
        body_items = "<p>기준 기간 내 신규 등록된 항목이 없습니다.</p>"

    notion_html = ""
    if NOTION_PAGE_URL and NOTION_PAGE_URL.startswith("http"):
        notion_html = f"""
        <div style="border:1px solid #d6e0ff;border-radius:8px;padding:10px 14px;margin-bottom:16px">
          과거 수집 내역은 노션에서 확인할 수 있습니다.<br>
          <a href="{NOTION_PAGE_URL}" style="font-weight:bold">&#128214; 노션 바로가기</a>
        </div>
        """

    fail_html = ""
    if failed_boards:
        fail_list = html.escape(", ".join(failed_boards))
        fail_html = (
            f"<hr style='border:none;border-top:1px solid #eee;margin:18px 0 8px 0'>"
            f"<p style='margin:0'>"
            f"수집 실패 게시판: {fail_list}<br>"
            f"(네트워크 차단 또는 사이트 장애 가능성 — 해당 게시판의 신규 글이 누락되었을 수 있습니다)</p>"
        )

    body = f"""
    <html><body style="{BASE_FONT};max-width:680px">
      <h2 style="font-weight:bold;margin:0 0 12px 0">방미통위 모니터링 결과 ({today_str})</h2>
      {notion_html}
      {body_items}
      {fail_html}
    </body></html>
    """

    recipients = [addr.strip() for addr in MAIL_TO.split(",") if addr.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=60) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_APP_PASSWORD)
        server.sendmail(SMTP_USER, recipients, msg.as_string())

    print(f"메일 발송 완료: {subject} -> {len(recipients)}명")

# END OF FILE