import os
import re
import json
from email.utils import parseaddr

FALLBACK_ALLOWED = {
    "telefonia": {
        "tim": ["tim.com.br", "tim.com"],
        "claro": ["claro.com.br"],
        "vivo": ["vivo.com.br"],
        "oi": ["oi.com.br"]
    },
    "bancos": {
        "itau": ["itau.com.br"],
        "bradesco": ["bradesco.com.br"],
        "santander": ["santander.com.br"],
        "banco_do_brasil": ["bb.com.br"],
        "caixa": ["caixa.gov.br"],
        "nubank": ["nubank.com.br"],
        "btg_pactual": ["btgpactual.com"],
        "original": ["original.com.br"],
        "inter": ["bancointer.com.br"]
    },
    "cartao_credito_e_pagamentos": {
        "c6bank": ["c6bank.com.br"],
        "pagseguro": ["pagseguro.com.br"],
        "mercado_pago": ["mercadopago.com", "mercadopago.com.br"],
        "paypal": ["paypal.com", "paypal.com.br"],
        "picpay": ["picpay.com"]
    },
    "credito_e_emprestimos": {
        "serasa": ["serasa.com.br"],
        "bmg": ["bancobmg.com.br"],
        "safra": ["safra.com.br"]
    },
    "planos_de_saude": {
        "amil": ["amil.com.br"],
        "unimed": ["unimed.coop.br"],
        "hapvida": ["hapvida.com.br"],
        "bradesco_saude": ["bradescoseguros.com.br"],
        "sulamerica": ["sulamericaseguros.com.br"]
    },
    "varejo_digital_e_servicos": {
        "mercado_livre": ["mercadolivre.com.br"],
        "magalu": ["magazineluiza.com.br"],
        "americanas": ["americanas.com.br"],
        "submarino": ["submarino.com.br"],
        "shopee": ["shopee.com.br"],
        "amazon": ["amazon.com", "amazon.com.br"]
    }
}

_ALLOWED = None
_ALLOWED_PATH = None

def load_allowed_senders(path="allowed_senders.json"):
    global _ALLOWED, _ALLOWED_PATH
    if _ALLOWED is not None and _ALLOWED_PATH == path:
        return _ALLOWED
    _ALLOWED_PATH = path
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _ALLOWED = json.load(f)
        else:
            _ALLOWED = FALLBACK_ALLOWED
    except Exception:
        _ALLOWED = FALLBACK_ALLOWED
    return _ALLOWED

def _normalize_display_name(display_name: str) -> str:
    return (display_name or "").strip().lower()

def _extract_email_domain(email_address: str) -> str:
    if not email_address:
        return ""
    _, addr = parseaddr(email_address)
    if "@" in addr:
        return addr.split("@")[-1].lower()
    return ""

BRAND_PATTERNS = {
    "tim": re.compile(r"(?i)(^|[\W_])tim([\W_]|$)"),
    "claro": re.compile(r"(?i)(^|[\W_])claro([\W_]|$)"),
    "vivo": re.compile(r"(?i)(^|[\W_])vivo([\W_]|$)"),
    "oi": re.compile(r"(?i)(^|[\W_])oi([\W_]|$)"),
    "paypal": re.compile(r"(?i)(^|[\W_])paypal([\W_]|$)"),
    "itau": re.compile(r"(?i)(^|[\W_])ita[uú]([\W_]|$)"),
    "bradesco": re.compile(r"(?i)(^|[\W_])bradesco([\W_]|$)"),
    "santander": re.compile(r"(?i)(^|[\W_])santander([\W_]|$)"),
    "banco_do_brasil": re.compile(r"(?i)(^|[\W_])(banco do brasil|bb)([\W_]|$)"),
    "caixa": re.compile(r"(?i)(^|[\W_])caixa([\W_]|$)"),
    "nubank": re.compile(r"(?i)(^|[\W_])nubank([\W_]|$)")
}

def _candidate_brands(text: str):
    t = (text or "")
    found = set()
    for brand, rgx in BRAND_PATTERNS.items():
        if rgx.search(t):
            found.add(brand)
    return found

def detect_brand_impersonation(meta: dict, content_text: str, allowed_path: str = "allowed_senders.json"):
    allowed = load_allowed_senders(allowed_path)

    display = (meta.get("from") or "")
    subject = (meta.get("subject") or "")
    from_reg = (meta.get("from_registered_domain") or "").lower()
    reply_reg = (meta.get("reply_to_registered_domain") or "").lower()

    scan_text = " ".join([display, subject, content_text or ""])
    candidates = _candidate_brands(scan_text)

    brand_to_domains = {}
    for _cat, brands in (allowed or {}).items():
        for brand_key, domains in (brands or {}).items():
            brand_to_domains[brand_key.lower()] = [d.lower() for d in domains]

    def canonical(b: str) -> str:
        b = b.lower().strip()
        mapping = {"itaú": "itau", "banco do brasil": "banco_do_brasil", "bb": "banco_do_brasil"}
        return mapping.get(b, b.replace(" ", "_"))

    # Se não há marcas detectadas, ainda informamos brand_detected=False
    if not candidates:
        return {
            "detected": False,
            "brand_detected": False,
            "critical_impersonation": False,
            "brand": None,
            "from_domain": from_reg,
            "official_domains": [],
            "reason": ""
        }

    # Para cada marca candidata, checa domínios oficiais
    for c in candidates:
        canon = canonical(c)
        official = brand_to_domains.get(canon, [])

        # Se temos from/reply e domínios oficiais → aplica regra crítica
        if official:
            if from_reg and all(not from_reg.endswith(od) for od in official):
                return {
                    "detected": True,
                    "brand_detected": True,
                    "critical_impersonation": True,
                    "brand": canon,
                    "from_domain": from_reg,
                    "official_domains": official,
                    "reason": f"Impersonation de marca: '{c.upper()}' mencionado, mas remetente é '{from_reg}', fora dos domínios oficiais {official}."
                }
            if reply_reg and all(not reply_reg.endswith(od) for od in official):
                return {
                    "detected": True,
                    "brand_detected": True,
                    "critical_impersonation": True,
                    "brand": canon,
                    "from_domain": from_reg,
                    "official_domains": official,
                    "reason": f"Impersonation de marca: reply-to '{reply_reg}' não pertence aos domínios oficiais {official}."
                }

    # Marca detectada, mas sem violação crítica por falta de contexto de domínio
    first = list(candidates)[0]
    return {
        "detected": True,
        "brand_detected": True,
        "critical_impersonation": False,
        "brand": first,
        "from_domain": from_reg,
        "official_domains": brand_to_domains.get(first, []),
        "reason": ""
    }
