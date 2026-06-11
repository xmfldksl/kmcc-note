import os

# 방송미디어통신위원회(KMCC) 기본 도메인
RSS_BASE_URL = "https://www.kmcc.go.kr"

BOARDS = {
    "공지사항": {"url": "https://www.kmcc.go.kr/user.do?page=A05020000&dc=K05020000&boardId=1112"},
    "보도자료": {"url": "https://www.kmcc.go.kr/user.do?page=A05030000&dc=K05030000&boardId=1113"},
    "언론보도대응": {"url": "https://www.kmcc.go.kr/user.do?page=A05030500&dc=K05035500&boardId=1171"},
    "의사일정": {"url": "https://www.kmcc.go.kr/user.do?page=A02010100&dc=K02010100&boardId=1003"},
    "심결정보": {"url": "https://www.kmcc.go.kr/user.do?page=A02010800&dc=K02010800&boardId=1119"},
    "방송정책": {"url": "https://www.kmcc.go.kr/user.do?page=A02020400&dc=K02020400&boardId=1006"},
    "이용자정책": {"url": "https://www.kmcc.go.kr/user.do?page=A02020600&dc=K02020600&boardId=1008"},
    "입법예고": {"url": "https://www.kmcc.go.kr/user.do?page=A02030900&dc=K02030900&boardId=1101"},
    "법령개정": {"url": "https://www.kmcc.go.kr/user.do?page=A02031000&dc=K02031000"},
    "정책연구": {"url": "https://www.kmcc.go.kr/user.do?page=A02160300&dc=K02160300&boardId=1022"},
    "연차보고서": {"url": "https://www.kmcc.go.kr/user.do?page=A02050300&dc=K02050300&boardId=1078"},
    "기타보고서": {"url": "https://www.kmcc.go.kr/user.do?page=A02050200&dc=K02050200&boardId=1025"},
}

HIGH_PRIORITY_KEYWORDS = ["홈쇼핑", "재승인", "T커머스", "티커머스", "GS샵", "GSSHOP", "GSMYSHOP"]
INCLUDE_KEYWORDS = ["GS리테일", "지에스리테일", "GS홈쇼핑", "지에스홈쇼핑", "심사청문회", "방송채널사용사업자"]
EXCLUDE_KEYWORDS = []

SEND_EMPTY_MAIL = True

# --- 테스트 모드: 쉼표로 구분된 게시판 이름이 있으면 해당 게시판만 실행 ---
TEST_BOARDS = os.getenv("TEST_BOARDS", "").strip()

# --- 메일 설정 ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")
MAIL_TO = os.getenv("MAIL_TO")

# --- Gemini 요약 설정 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
# 첨부파일 추출 텍스트를 이 글자 수까지만 Gemini에 전달 (무료 등급 한도 보호)
MAX_EXTRACT_CHARS = 30000
# Gemini 호출 사이 대기 시간(초): 무료 등급 분당 요청 제한 회피
GEMINI_CALL_INTERVAL = 7
# 첨부파일 처리 우선순위 (앞에 있을수록 우선)
ATTACHMENT_PRIORITY = [".pdf", ".hwpx", ".hwp"]

# END OF FILE