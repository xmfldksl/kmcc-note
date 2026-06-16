# KMCC Note

A monitoring system that automatically collects posts from the major boards of the Korea Media & Communications Commission (KMCC) website, summarizes keyword-matching posts with AI, and delivers them via **email** and a **Notion database**.

It is designed to track daily policy trends and committee schedules on specific topics such as home shopping, re-approval, transmission fees, and cable broadcasting (SO).

---

## Features

- **Automated collection**: Crawls 12 boards every weekday at noon (KST) via GitHub Actions.
- **Keyword filtering**: Always collects committee schedules and committee-result press releases; other posts are filtered by predefined keywords (title + body).
- **Attachment summarization**: Downloads post attachments (PDF / HWPX / HWP), extracts the text, and summarizes it with the Gemini API. When a filename is garbled, the file format is detected by its content signature (magic bytes).
- **Meeting summary format**: Meeting documents such as agendas, minutes, and transcripts are summarized in a fixed format for internal sharing (committee session number, per-item resolution/report classification, etc.).
- **Email delivery**: Sends results as an HTML email, with a Notion archive link at the top and any failed boards listed at the bottom.
- **Notion archive**: Stores filtered posts in a Notion database, including the full summary, attachments (uploaded directly for supported formats, original link for unsupported ones), and an original-post link, while preventing duplicates by title + date.

---

## Architecture

\`\`\`
src/
├── config.py          Settings (board list, keywords, model, env vars)
├── crawler.py         Board list / detail page crawling
├── attachment.py      Attachment download & text extraction (PDF/HWPX/HWP)
├── summarizer.py      Gemini API summarization (model chain, meeting format)
├── filter.py          Keyword filtering
├── storage.py         Duplicate-prevention record (seen_posts.txt)
├── mailer.py          SMTP email delivery
├── notion_archiver.py Notion database archiving
└── main.py            Main execution flow

.github/workflows/
└── scraper.yml        GitHub Actions schedule
\`\`\`

### Flow

1. Read post dates from the board list and select only posts after the reference date (minimizing requests)
2. Collect body and attachments from the detail pages of target posts
3. Pass only mandatory-collection posts or keyword-matching posts
4. Extract attachments and summarize with Gemini (one combined call per post)
5. Email and archive non-duplicate posts to Notion

---

## Installation & Usage

### Requirements

- Python 3.12 or higher

### Install dependencies

\`\`\`bash
pip install -r requirements.txt
\`\`\`

### Environment variables

Set the following as environment variables (or GitHub secrets).

| Variable | Purpose |
|---|---|
| \`SMTP_USER\` | Sender Gmail address |
| \`SMTP_APP_PASSWORD\` | Gmail app password |
| \`MAIL_TO\` | Recipient email (comma-separated for multiple) |
| \`GEMINI_API_KEY\` | Google AI Studio API key |
| \`NOTION_TOKEN\` | Notion integration token |
| \`NOTION_DATABASE_ID\` | Notion database ID |

### Run

\`\`\`bash
python -m src.main
\`\`\`

---

## Execution Modes

Behavior is controlled by environment variables.

| Variable | Description |
|---|---|
| \`TEST_BOARDS\` | Comma-separated board names. Runs only those boards when set (all boards if empty) |
| \`BACKFILL_FROM\` | \`YYYY-MM-DD\`. When set, collects all past posts after that date by paging through the board |
| \`SKIP_MAIL\` | \`1\` skips email delivery (Notion archiving only) |

**Backfill** (retroactive collection): when the daily API quota is exhausted, it records up to the processed point and stops. Re-running with the same settings after the quota resets resumes from where it stopped.

---

## Notion Database Setup

The Notion database must have the following properties for archiving.

| Property | Type |
|---|---|
| 제목 (Title) | Title |
| 게시판 (Board) | Select |
| 날짜 (Date) | Date |
| 키워드 (Keyword) | Multi-select |
| 원문보기 (Original) | URL |
| 요약보기 (Summary) | URL |

The integration must be connected to the database page for API access.

---

## Operational Notes

- Scheduled runs are performed by GitHub Actions (weekdays at noon).
- Because Korean public-sector sites tend to block overseas IP ranges, large-scale collection (backfill) is recommended to run from a domestic IP environment.
- To cope with the Gemini free-tier daily limit, a lightweight model is used first and automatically switches to a higher-tier model when the quota is exhausted.

---

## Tech Stack

- **Language**: Python 3.12
- **Crawling**: curl_cffi (browser impersonation), BeautifulSoup
- **Document processing**: pdfplumber (PDF), olefile (HWP), standard zipfile (HWPX)
- **AI summarization**: Google Gemini API
- **Output**: SMTP (email), Notion API (archive)
- **Automation**: GitHub Actions

<br>

---
---

<br>

# KMCC Note (한국어)

방송미디어통신위원회(KMCC) 홈페이지의 주요 게시판을 자동으로 수집해, 키워드에 해당하는 글을 AI로 요약하고 **이메일 발송**과 **노션 데이터베이스 적재**까지 처리하는 모니터링 시스템입니다.

홈쇼핑·재승인·송출수수료·종합유선방송 등 특정 주제의 정책 동향과 위원회 의사일정을 매일 자동으로 추적하는 것을 목적으로 합니다.

---

## 주요 기능

- **자동 수집**: 깃허브 액션으로 평일 정오(KST)에 12개 게시판을 자동 크롤링합니다.
- **키워드 필터링**: 의사일정과 위원회 결과 보도자료는 필수 수집하고, 그 외 글은 사전 정의한 키워드(제목+본문)로 선별합니다.
- **첨부파일 본문 요약**: 게시글 첨부파일(PDF / HWPX / HWP)을 직접 다운로드해 본문을 추출하고 Gemini API로 요약합니다. 파일명이 깨진 경우 내용 시그니처(매직 바이트)로 형식을 판별합니다.
- **회의 요약 양식**: 의사일정·회의록·속기록 등 회의 문서는 부서 공유용 정형 양식(회의 차수, 안건별 의결/보고 구분 등)으로 요약합니다.
- **이메일 발송**: 수집 결과를 HTML 메일로 발송하며, 상단에 노션 아카이브 링크, 하단에 수집 실패 게시판을 표시합니다.
- **노션 아카이브**: 필터를 통과한 글을 노션 DB에 적재합니다. 요약 전문, 첨부파일(지원 형식은 직접 업로드, 미지원 형식은 원문 링크), 원문 보기 링크를 함께 저장하고 제목+날짜로 중복을 차단합니다.

---

## 시스템 구조

\`\`\`
src/
├── config.py          설정 (게시판 목록, 키워드, 모델, 환경변수)
├── crawler.py         게시판 목록·상세 페이지 크롤링
├── attachment.py      첨부파일 다운로드 및 텍스트 추출 (PDF/HWPX/HWP)
├── summarizer.py      Gemini API 요약 (모델 체인, 회의 양식)
├── filter.py          키워드 필터링
├── storage.py         중복 방지 기록 (seen_posts.txt)
├── mailer.py          SMTP 이메일 발송
├── notion_archiver.py 노션 데이터베이스 적재
└── main.py            전체 실행 흐름

.github/workflows/
└── scraper.yml        깃허브 액션 스케줄 설정
\`\`\`

### 처리 흐름

1. 게시판 목록에서 등록일을 읽어 기준일 이후 글만 선별 (요청량 최소화)
2. 대상 글의 상세 페이지에서 본문·첨부파일 수집
3. 필수 수집 대상 또는 키워드 일치 글만 통과
4. 첨부파일 추출 후 Gemini로 요약 (게시글당 1회 통합 호출)
5. 중복이 아닌 글을 이메일 발송 + 노션 적재

---

## 설치 및 실행

### 요구 사항

- Python 3.12 이상

### 의존성 설치

\`\`\`bash
pip install -r requirements.txt
\`\`\`

### 환경변수

다음 값을 환경변수(또는 깃허브 시크릿)로 설정합니다.

| 변수명 | 용도 |
|---|---|
| \`SMTP_USER\` | 발신 Gmail 주소 |
| \`SMTP_APP_PASSWORD\` | Gmail 앱 비밀번호 |
| \`MAIL_TO\` | 수신 이메일 주소 (쉼표로 복수 지정 가능) |
| \`GEMINI_API_KEY\` | Google AI Studio API 키 |
| \`NOTION_TOKEN\` | 노션 통합(Integration) 토큰 |
| \`NOTION_DATABASE_ID\` | 노션 데이터베이스 ID |

### 실행

\`\`\`bash
python -m src.main
\`\`\`

---

## 실행 모드

환경변수로 동작을 제어합니다.

| 변수명 | 설명 |
|---|---|
| \`TEST_BOARDS\` | 쉼표로 구분된 게시판 이름. 지정 시 해당 게시판만 실행 (비우면 전체) |
| \`BACKFILL_FROM\` | \`YYYY-MM-DD\` 형식. 지정 시 해당 날짜 이후의 과거 글을 페이지를 넘기며 전부 수집 |
| \`SKIP_MAIL\` | \`1\`이면 이메일 발송을 생략 (노션 적재만 수행) |

**백필(과거 데이터 소급 수집)** 은 일일 API 한도가 소진되면 처리한 지점까지만 기록하고 중단하며, 한도 초기화 후 같은 설정으로 재실행하면 중단 지점부터 이어서 수집합니다.

---

## 노션 데이터베이스 구성

적재를 위해 노션 데이터베이스에 다음 속성이 필요합니다.

| 속성명 | 타입 |
|---|---|
| 제목 | 제목(Title) |
| 게시판 | 선택(Select) |
| 날짜 | 날짜(Date) |
| 키워드 | 다중 선택(Multi-select) |
| 원문보기 | URL |
| 요약보기 | URL |

생성한 통합(Integration)을 해당 데이터베이스 페이지에 연결해야 API 접근이 가능합니다.

---

## 운영 참고

- 정기 실행은 깃허브 액션(평일 정오)에서 수행합니다.
- 한국 공공기관 사이트의 해외 IP 차단 특성상, 대량 수집(백필)은 국내 IP 환경에서 실행하는 것을 권장합니다.
- Gemini 무료 등급의 일일 한도에 대응해 경량 모델을 우선 사용하고, 한도 소진 시 상위 모델로 자동 전환합니다.

---

## 기술 스택

- **언어**: Python 3.12
- **크롤링**: curl_cffi (브라우저 위장), BeautifulSoup
- **문서 처리**: pdfplumber (PDF), olefile (HWP), 표준 zipfile (HWPX)
- **AI 요약**: Google Gemini API
- **출력**: SMTP (이메일), Notion API (아카이브)
- **자동화**: GitHub Actions