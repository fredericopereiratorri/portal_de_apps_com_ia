import re

SAFE_DOMAINS = {
    "bb.com.br", "bancobrasil.com.br", "itau.com.br", "gmail.com",
    "outlook.com", "gov.br", "nubank.com.br", "bradesco.com.br"
}

TRACKING_DOMAINS_HINT = {
    "p-email.net", "pontaltech.com.br", "sendgrid.net", "mailchimpapp.com",
    "mandrillapp.com", "click.email", "emltrk.com"
}

SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "ow.ly", "buff.ly", "goo.gl"
}

PRIZE_CTA_PATTERN = re.compile(
    r"(sorteio|pr[eê]mio|ganhador|ganhe|parab[eé]ns|clique\s+e\s+participe|resgate|promo[cç][aã]o|vencedor)",
    re.I
)

def _domain_safe(meta):
    import re as _re
    u = (meta or {}).get("final_url") or (meta or {}).get("url") or ""
    m = _re.search(r"https?://([^/]+)/?", u)
    if not m:
        return False
    host = m.group(1).lower()
    return any(host.endswith(d) for d in SAFE_DOMAINS)

def _benign_signals(text, meta):
    text_lc = (text or "").lower()
    benign = 0.0
    notes = []

    if meta.get("url_accessible") and str(meta.get("status_code")).startswith("2"):
        if meta.get("final_url", "").startswith("https://") and not meta.get("was_redirect_chain"):
            benign += 0.15; notes.append("link https estável (2xx).")

    if _domain_safe(meta):
        benign += 0.20; notes.append("domínio conhecido/esperado.")

    if meta.get("domain_whitelisted"):
        benign += 0.30; notes.append("domínio em whitelist.")
    if meta.get("phrase_whitelisted"):
        benign += 0.20; notes.append("frase em whitelist.")

    if any(k in text_lc for k in ["atenciosamente", "att.", "assinado digitalmente", "confidencialidade:", "assinatura eletrônica"]):
        benign += 0.05; notes.append("linguagem formal / assinatura corporativa.")

    if not re.search(r"(clique|atualiz(e|ar)|confirm(e|ar)|senha|token|c[oó]digo|pix|documento|foto|selfie|whatsapp|wa\.me)", text_lc):
        benign += 0.10; notes.append("sem pedido de ação sensível.")

    if len(text_lc) > 80 and "http" not in text_lc:
        benign += 0.10; notes.append("sem links no corpo do texto.")

    return benign, notes

def heuristic_score(text, meta=None):
    meta = meta or {}
    t = (text or "").lower()

    score = 0.0
    red = []

    # Urgência/ameaça
    if re.search(r"(urgente|bloquead[oa]|suspens[ao]|24h|2 horas|imediatamente|encerrada permanentemente|alerta severo)", t):
        score += 0.22; red.append("tom de urgência/ameaça.")

    # Ação sensível
    if re.search(r"(clique|confirm(e|ar)|atualiz(e|ar)|senha|token|c[oó]digo|pix|documento|foto|selfie|whatsapp|wa\.me)", t):
        score += 0.25; red.append("pedido de ação sensível/contato externo.")

    # Encurtadores
    link_domains = set((meta.get("link_domains") or []))
    if any(d in SHORTENER_DOMAINS for d in link_domains):
        score += 0.18; red.append("uso de encurtador de link.")

    # Link inacessível
    if meta.get("url_accessible") is False:
        score += 0.12; red.append("link inacessível.")

    # TLD incomum
    if meta.get("from_domain_suspect"):
        score += 0.15; red.append("remetente/domínio com TLD incomum.")

    # ESP/tracking
    if any(d in TRACKING_DOMAINS_HINT for d in link_domains):
        score += 0.06; red.append("links de tracking/ESP.")

    # IMAGEM: pouco texto
    if (meta.get("source_type") == "image") and (meta.get("ocr_text_len", 0) < 20):
        score += 0.05; red.append("pouco texto reconhecido (OCR).")

    # NOVO: PRÊMIO/SORTEIO/CTA
    if PRIZE_CTA_PATTERN.search(t):
        score += 0.22; red.append("gatilhos de prêmio/sorteio/CTA.")

    # Sinal explícito de impersonation previamente detectado (não crítico)
    if meta.get("brand_impersonation_detected"):
        score += 0.30; red.append(meta.get("brand_impersonation_reason", "impersonation de marca."))

    # IMAGEM + PRÊMIO/SORTEIO tem mais peso
    if (meta.get("source_type") == "image") and PRIZE_CTA_PATTERN.search(t):
        score += 0.18; red.append("imagem promocional suspeita (phishing visual).")

    benign, notes = _benign_signals(text, meta)
    score = max(0.0, score - benign)
    score = min(1.0, score)

    return {
        "score": score,
        "red_flags": red,
        "benign_notes": notes,
    }
