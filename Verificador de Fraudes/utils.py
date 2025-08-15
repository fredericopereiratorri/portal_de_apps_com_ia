import html

def safe_html_snippet(text: str, max_len: int = 1000):
    if not text:
        return "<pre class='snippet'>(vazio)</pre>"
    s = text.strip()
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return "<pre class='snippet'>" + html.escape(s) + "</pre>"
