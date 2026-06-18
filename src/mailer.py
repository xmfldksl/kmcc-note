import smtplib
import html
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.config import (
    SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_APP_PASSWORD, MAIL_TO,
    NOTION_PAGE_URL,
)


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
        doc_links = f"<p style='margin:4px 0'><b>원본 문서:</b></p><ul>{doc_links}</ul>"

    kw_line = f"<p style='margin:4px 0;color:#888'>일치 키워드: {keywords}</p>" if keywords else ""

    return f"""
    <div style="border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:14px">
      <p style="margin:0 0 6px 0">
        <span style="background:#eef;border-radius:4px;padding:2px 6px;font-size:12px">{board}</span>
        <span style="color:#888;font-size:12px">{date}</span>
      </p>
      <p style="margin:0 0 8px 0;font-size:15px"><b><a href="{url}">{title}</a></b></p>
      {kw_line}
      <div style="background:#f8f8f8;border-radius:6px;padding:10px;font-size:13px;line-height:1.6">
        {summary}
      </div>
      {doc_links}
    </div>
    """


def send_mail(items, today_str, failed_boards=None):
    """수집 결과를 HTML 메일로 발송한다.

    - 상단: 노션 아카이브 안내 (NOTION_PAGE_URL 설정 시)
    - 하단: 최종 수집 실패 게시판 표시
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
        <div style="background:#f0f4ff;border:1px solid #d6e0ff;border-radius:8px;
                    padding:10px 14px;margin-bottom:16px;font-size:13px">
          상세정보 및 과거 수집 내역은 노션 아카이브에서 확인할 수 있습니다.<br>
          <a href="{NOTION_PAGE_URL}" style="font-weight:bold">&#128214; 아카이브 바로가기</a>
        </div>
        """

    fail_html = ""
    if failed_boards:
        fail_list = html.escape(", ".join(failed_boards))
        fail_html = (
            f"<hr style='border:none;border-top:1px solid #eee;margin:18px 0 8px 0'>"
            f"<p style='color:#c00;font-size:12px;margin:0'>"
            f"수집 실패 게시판: {fail_list}<br>"
            f"(네트워크 차단 또는 사이트 장애 가능성 — 해당 게시판의 신규 글이 누락되었을 수 있습니다)</p>"
        )

    body = f"""
    <html><body style="font-family:'Malgun Gothic',sans-serif;max-width:680px">
      <h2 style="font-size:17px">방미통위 모니터링 결과 ({today_str})</h2>
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