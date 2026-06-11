import io
import re
import html
import hashlib
import zipfile
import zlib
import struct
import time
import random
import os
import urllib3
import olefile
from curl_cffi import requests
import pdfplumber
from src.config import ATTACHMENT_PRIORITY, MAX_EXTRACT_CHARS
from src.crawler import DEFAULT_HEADERS, PROXY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _is_garbled(name):
    """인코딩 깨짐(대체 문자 포함) 여부를 판별한다."""
    return "\ufffd" in name


def _sniff_ext(data):
    """파일 내용의 시그니처(매직 바이트)로 형식을 판별한다."""
    if data[:5] == b"%PDF-":
        return ".pdf"
    if data[:2] == b"PK":
        return ".hwpx"  # ZIP 기반 (HWPX)
    if data[:8] == OLE_SIGNATURE:
        return ".hwp"   # OLE 기반 (HWP 5.0)
    return None


def group_documents(attachments):
    """첨부파일을 문서 단위(확장자 제외 파일명)로 묶고,
    각 문서마다 우선순위(PDF > HWPX > HWP)가 가장 높은 파일 1개를 고른다.
    확장자를 알 수 없는 파일(파일명 깨짐 등)은 다운로드 후 시그니처로 판별한다(ext=None).
    """
    groups = {}
    for att in attachments:
        name = att.get('name', '').strip()
        if not name:
            continue
        base, ext = os.path.splitext(name)
        base = base.strip()
        ext = ext.lower()
        groups.setdefault(base, []).append({'name': name, 'url': att['url'], 'ext': ext})

    selected = []
    unknown_count = 0
    for base, files in groups.items():
        chosen = None
        for ext in ATTACHMENT_PRIORITY:
            for f in files:
                if f['ext'] == ext:
                    chosen = f
                    break
            if chosen:
                break

        if chosen is None:
            # 확장자 매칭 실패: 깨진 파일명 등 → 내용 시그니처로 판별하기 위해 포함
            chosen = dict(files[0])
            chosen['ext'] = None

        doc_name = base
        if _is_garbled(doc_name):
            unknown_count += 1
            doc_name = f"첨부문서 {unknown_count}"

        selected.append({
            'doc_name': doc_name,
            'name': chosen['name'] if not _is_garbled(chosen['name']) else doc_name,
            'url': chosen['url'],
            'ext': chosen['ext'],
        })
    return selected


def download_file(url):
    """첨부파일을 다운로드해 바이트로 반환한다. 실패 시 None."""
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(random.uniform(3.0, 6.0))
            response = requests.get(
                url,
                impersonate="chrome116",
                headers=DEFAULT_HEADERS,
                proxies=PROXY,
                timeout=60,
                verify=False
            )
            if response.status_code == 200 and response.content:
                return response.content
            print(f"    -> 다운로드 응답 이상 (HTTP {response.status_code})")
        except Exception as e:
            print(f"    -> 다운로드 에러 (시도 {attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(5.0)
    return None


def extract_pdf_text(data):
    """PDF 바이트에서 텍스트를 추출한다."""
    texts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
    return "\n".join(texts)


def extract_hwpx_text(data):
    """HWPX(ZIP+XML) 바이트에서 텍스트를 추출한다."""
    texts = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        section_names = sorted(
            n for n in zf.namelist()
            if n.startswith("Contents/section") and n.endswith(".xml")
        )
        for name in section_names:
            xml = zf.read(name).decode("utf-8", errors="ignore")
            for frag in re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", xml, re.DOTALL):
                frag = re.sub(r"<[^>]+>", "", frag)
                frag = html.unescape(frag).strip()
                if frag:
                    texts.append(frag)
    return "\n".join(texts)


def extract_hwp_text(data):
    """HWP(한글 5.0 바이너리) 바이트에서 본문 텍스트를 추출한다.

    OLE 컨테이너의 BodyText 섹션 스트림을 zlib으로 풀고,
    문단 텍스트 레코드(HWPTAG_PARA_TEXT=67)의 UTF-16 텍스트를 읽는다.
    """
    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        header = ole.openstream("FileHeader").read()
        is_compressed = (header[36] & 1) == 1

        sections = sorted(
            entry for entry in ole.listdir()
            if entry and entry[0] == "BodyText"
        )

        texts = []
        for entry in sections:
            stream = ole.openstream(entry).read()
            if is_compressed:
                stream = zlib.decompress(stream, -15)

            i, size = 0, len(stream)
            while i + 4 <= size:
                header_val = struct.unpack_from("<I", stream, i)[0]
                tag = header_val & 0x3FF
                length = (header_val >> 20) & 0xFFF
                i += 4
                if length == 0xFFF:
                    length = struct.unpack_from("<I", stream, i)[0]
                    i += 4
                if tag == 67:  # 문단 텍스트
                    raw = stream[i:i + length]
                    text = raw.decode("utf-16-le", errors="ignore")
                    clean = "".join(
                        ch for ch in text
                        if ch.isprintable() or ch in "\n\t "
                    ).strip()
                    if clean:
                        texts.append(clean)
                i += length
        return "\n".join(texts)
    finally:
        ole.close()


def get_document_texts(item):
    """게시글의 모든 첨부 문서(문서 단위)에서 텍스트를 추출한다.

    - 확장자 불명 파일은 시그니처로 형식 판별
    - 같은 내용의 중복 문서(형식만 다른 경우)는 1개만 사용
    - 각 결과에 원본 파일 바이트(data)도 포함 (노션 업로드 재사용)
    """
    attachments = item.get('attachments', [])
    if not attachments:
        return []

    documents = group_documents(attachments)
    results = []
    seen_text_keys = set()

    for doc in documents:
        print(f"    -> 첨부파일 다운로드: {doc['name'][:30]}")
        data = download_file(doc['url'])
        if data is None:
            continue

        ext = doc['ext'] or _sniff_ext(data)
        if ext not in (".pdf", ".hwpx", ".hwp"):
            print(f"    -> [건너뜀] 지원하지 않는 파일 형식: {doc['name'][:30]}")
            continue

        try:
            if ext == ".pdf":
                text = extract_pdf_text(data)
            elif ext == ".hwpx":
                text = extract_hwpx_text(data)
            else:
                text = extract_hwp_text(data)
        except Exception as e:
            print(f"    -> 텍스트 추출 실패 ({ext}): {e}")
            continue

        text = re.sub(r"\s{3,}", " ", text).strip()
        if len(text) < 50:
            print("    -> 추출 텍스트가 너무 짧아 사용하지 않음 (스캔본 또는 배포용 문서 가능성)")
            continue

        if len(text) > MAX_EXTRACT_CHARS:
            text = text[:MAX_EXTRACT_CHARS]

        # 같은 내용(형식만 다른 중복 문서)은 1개만 사용
        text_key = hashlib.sha256(text[:1000].encode("utf-8")).hexdigest()
        if text_key in seen_text_keys:
            print(f"    -> [건너뜀] 동일 내용의 중복 문서: {doc['doc_name'][:20]}")
            continue
        seen_text_keys.add(text_key)

        print(f"    -> 텍스트 추출 완료 ({len(text)}자): {doc['doc_name'][:20]}")
        results.append({
            'doc_name': doc['doc_name'],
            'file_name': doc['name'],
            'url': doc['url'],
            'text': text,
            'data': data,
        })

    return results

# END OF FILE