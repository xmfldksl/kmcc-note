import io
import re
import html
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


def group_documents(attachments):
    """첨부파일을 문서 단위(확장자 제외 파일명)로 묶고,
    각 문서마다 우선순위(PDF > HWPX > HWP)가 가장 높은 파일 1개를 고른다.
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
    for base, files in groups.items():
        chosen = None
        for ext in ATTACHMENT_PRIORITY:
            for f in files:
                if f['ext'] == ext:
                    chosen = f
                    break
            if chosen:
                break
        if chosen:
            selected.append({
                'doc_name': base,
                'name': chosen['name'],
                'url': chosen['url'],
                'ext': chosen['ext'],
            })
        else:
            print(f"    -> [건너뜀] 지원 형식 아님: {base[:30]}")
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

    각 결과에 원본 파일 바이트(data)도 포함해 노션 업로드에 재사용한다.
    """
    attachments = item.get('attachments', [])
    if not attachments:
        return []

    documents = group_documents(attachments)
    results = []

    for doc in documents:
        print(f"    -> 첨부파일 다운로드: {doc['name'][:30]}")
        data = download_file(doc['url'])
        if data is None:
            continue

        try:
            if doc['ext'] == ".pdf":
                text = extract_pdf_text(data)
            elif doc['ext'] == ".hwpx":
                text = extract_hwpx_text(data)
            else:
                text = extract_hwp_text(data)
        except Exception as e:
            print(f"    -> 텍스트 추출 실패 ({doc['ext']}): {e}")
            continue

        text = re.sub(r"\s{3,}", " ", text).strip()
        if len(text) < 50:
            print("    -> 추출 텍스트가 너무 짧아 사용하지 않음 (스캔본 또는 배포용 문서 가능성)")
            continue

        if len(text) > MAX_EXTRACT_CHARS:
            text = text[:MAX_EXTRACT_CHARS]

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