import hashlib
import os

SEEN_FILE = "seen_posts.txt"
MAX_RECORDS = 3000


def get_hash(*parts):
    """전달된 문자열들을 합쳐 SHA-256 해시를 만든다."""
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def load_seen():
    """기존 발송 기록(해시 목록)을 불러온다."""
    if not os.path.exists(SEEN_FILE):
        return []
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def save_seen(hashes):
    """발송 기록을 저장한다. 최근 MAX_RECORDS건만 유지."""
    trimmed = hashes[-MAX_RECORDS:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(trimmed) + "\n")
    print(f"발송 기록 저장 완료 ({len(trimmed)}건)")