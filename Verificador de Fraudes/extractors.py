import re
import io
import json
import email
import tldextract
import requests
from bs4 import BeautifulSoup
from html import unescape

REQ_TIMEOUT = 8
HEADERS = {"User-Agent": "Verificador de Fraudes/1.0 (+https://example.local)"}
URL_RX = re.compile(r"https?://[^\s)>'\"]+", re.I)

def _url_human_error(e):
    s = str(e)
    if "NameResolutionError" in s or "Failed to resolve" in s:
        return "não foi possível resolver o domínio (DNS)."
    if "ConnectTimeout" in s or "ReadTimeout" in s or "timeout" in s.lower():
        return "tempo de conexão esgotado."
    if "SSLError" in s:
        return "falha SSL/TLS."
    return s or "erro de rede."

def _extract_urls_from_text(text: str):
    urls = []
    for m in URL_RX.finditer(text or ""):
        urls.append(m.group(0))
    return urls

def _domain(url: str):
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""

def extract_text_from_url(url: str):
    meta = {"url": url}
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT, allow_redirects=True)
        meta["status_code"] = r.status_code
        meta["final_url"] = r.url
        meta["url_accessible"] = (200 <= r.status_code < 300)
        meta["was_redirect_chain"] = (len(r.history) > 1)

        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.string.strip() if soup.title and soup.title.string else "")
        meta["title"] = title

        for s in soup(["script","style","noscript"]): s.extract()

        links = []
        link_domains = []
        for a in soup.find_all("a"):
            href = a.get("href") or ""
            if href.startswith("http"):
                links.append(href)
                d = _domain(href)
                if d and d not in link_domains:
                    link_domains.append(d)
        meta["links"] = links[:200]
        meta["link_domains"] = link_domains[:50]

        text = " ".join(soup.get_text(separator=" ").split())
        extra = _extract_urls_from_text(text)
        for u in extra:
            if u not in meta["links"]:
                meta["links"].append(u)
                d = _domain(u)
                if d and d not in meta["link_domains"]:
                    meta["link_domains"].append(d)

        return text[:20000], meta

    except requests.RequestException as e:
        meta["url_accessible"] = False
        meta["url_error_human"] = _url_human_error(e)
        return f"(Falha ao acessar a URL: {meta['url_error_human']})", meta

def extract_text_from_eml(filelike: io.BytesIO):
    meta = {"source": "eml"}
    msg = email.message_from_bytes(filelike.read())

    meta["subject"] = msg.get("Subject", "")
    meta["from"] = msg.get("From", "")
    meta["reply_to"] = msg.get("Reply-To", "")
    meta["list_unsubscribe"] = msg.get("List-Unsubscribe", "") or msg.get("List-Unsubscribe-Post", "")

    from_raw = meta["from"]
    m = re.search(r'<[^@<]*@([^>]+)>', from_raw) or re.search(r'@([A-Za-z0-9\.\-\_]+)', from_raw)
    if m:
        domain = m.group(1).lower()
        ext = tldextract.extract(domain)
        regdom = ".".join([p for p in [ext.domain, ext.suffix] if p])
        meta["from_domain"] = domain
        meta["from_registered_domain"] = regdom
        meta["from_domain_suspect"] = (ext.suffix not in ("br","com","net","gov","org","edu"))

    if meta["reply_to"]:
        m2 = re.search(r'<[^@<]*@([^>]+)>', meta["reply_to"]) or re.search(r'@([A-Za-z0-9\.\-\_]+)', meta["reply_to"])
        if m2:
            rdom = m2.group(1).lower()
            rext = tldextract.extract(rdom)
            rreg = ".".join([p for p in [rext.domain, rext.suffix] if p])
            meta["reply_to_domain"] = rdom
            meta["reply_to_registered_domain"] = rreg

    body_plain = []
    html_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = (part.get_content_type() or "").lower()
            if ct.startswith("text/plain"):
                try:
                    body_plain.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore"))
                except Exception:
                    pass
            elif ct.startswith("text/html"):
                try:
                    html_parts.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore"))
                except Exception:
                    pass
    else:
        ct = (msg.get_content_type() or "").lower()
        try:
            if ct.startswith("text/html"):
                html_parts.append(msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore"))
            else:
                body_plain.append(msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="ignore"))
        except Exception:
            pass

    full_text = "\n".join(body_plain) if body_plain else ""

    links = []
    link_domains = []
    html_texts = []
    for h in html_parts:
        soup = BeautifulSoup(h, "html.parser")
        for s in soup(["script","style","noscript"]): s.extract()
        html_texts.append(soup.get_text(separator=" ", strip=True))
        for a in soup.find_all("a"):
            href = a.get("href") or ""
            if href.startswith("http"):
                href = unescape(href)
                links.append(href)
                d = _domain(href)
                if d and d not in link_domains:
                    link_domains.append(d)

    loose_urls = _extract_urls_from_text(full_text)
    for u in loose_urls:
        if u not in links:
            links.append(u)
            d = _domain(u)
            if d and d not in link_domains:
                link_domains.append(d)

    if html_texts:
        full_text = (full_text + "\n\n" + "\n\n".join(html_texts)).strip()

    meta["links"] = links[:300]
    meta["link_domains"] = link_domains[:80]

    return full_text[:20000], meta
