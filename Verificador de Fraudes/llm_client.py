import os
import re
import json
from urllib.parse import urlparse
from openai import OpenAI

def _domain_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""

def build_signal_summary(content: str, meta: dict) -> dict:
    meta = meta or {}
    content = content or ""

    link_domains = list(set(meta.get("link_domains") or []))
    reply_to = meta.get("reply_to") or ""
    reply_to_reg = (meta.get("reply_to_registered_domain") or "").lower()
    from_reg = (meta.get("from_registered_domain") or "").lower()

    has_wa = "wa.me" in link_domains
    has_tracking = any(d.endswith(("p-email.net","pontaltech.com.br","sendgrid.net","mailchimpapp.com","mandrillapp.com")) for d in link_domains)
    urgent = bool(re.search(r"\b(urgente|alerta severo|bloquead[oa]|suspens[ao]|imediat[ao])\b", content, re.I))
    asks_sensitive = bool(re.search(r"\b(clique|confirm(e|ar)|atualiz(e|ar)|senha|token|c[oó]digo|pix|documento|foto|selfie|whatsapp)\b", content, re.I))

    return {
        "subject": meta.get("subject",""),
        "from": meta.get("from",""),
        "from_registered_domain": from_reg,
        "reply_to": reply_to,
        "reply_to_registered_domain": reply_to_reg,
        "link_domains": link_domains[:80],
        "has_whatsapp_link": has_wa,
        "has_tracking_domains": has_tracking,
        "domain_whitelisted": bool(meta.get("domain_whitelisted")),
        "phrase_whitelisted": bool(meta.get("phrase_whitelisted")),
        "https_2xx_no_chain": bool(meta.get("url_accessible")) and str(meta.get("status_code","")).startswith("2") and not bool(meta.get("was_redirect_chain")),
        "final_url": meta.get("final_url") or meta.get("url") or "",
        "source_type": meta.get("source_type"),
        "ocr_text_len": meta.get("ocr_text_len", 0),
        "brand_impersonation_detected": bool(meta.get("brand_impersonation_detected")),
        "brand_impersonation_reason": meta.get("brand_impersonation_reason") or "",
        "content_excerpt": content[:1200]
    }

def llm_analyze(content, meta):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "label": "ok",
            "risk_score_llm": 0.2,
            "confidence_llm": 0.4,
            "red_flags": [],
            "explanation": "LLM desativado (sem OPENAI_API_KEY).",
            "actions": []
        }

    client = OpenAI(api_key=api_key)
    signals = build_signal_summary(content, meta)

    system_msg = {
        "role": "system",
        "content": (
            "Você é um analista de fraudes extremamente cauteloso. "
            "Marque 'suspeito' APENAS se houver pelo menos 2 sinais de risco consistentes. "
            "Marque 'fraude' se houver pelo menos 3 sinais ou evidência técnica crítica, "
            "como impersonation de marca (ex.: e-mail diz ser de uma marca famosa mas o domínio do remetente não é oficial). "
            "Sinais relevantes: urgência, pedido de ação sensível, link para WhatsApp (wa.me), domínios de tracking/ESP, reply-to divergente, "
            "impersonation de marca, links para domínios não-oficiais. "
            "Sinais benignos (domínio whitelisted, https 2xx sem redirecionamentos estranhos, ausência de pedido sensível) reduzem risco. "
            "Responda ESTRITAMENTE em JSON: "
            "{ \"label\": \"ok|suspeito|fraude\", \"risk_score_llm\": 0..1, \"confidence_llm\": 0..1, "
            "\"red_flags\": [\"...\"], \"explanation\": \"...\", \"actions\": [\"...\"] }"
        )
    }

    user_msg = {
        "role": "user",
        "content": "Analise o conteúdo e os sinais abaixo e classifique o risco:\n\n" + json.dumps(signals, ensure_ascii=False)
    }

    resp = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        messages=[system_msg, user_msg],
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        max_tokens=700,
    )

    raw = (resp.choices[0].message.content or "").strip()
    data = {
        "label": "ok",
        "risk_score_llm": 0.20,
        "confidence_llm": 0.40,
        "red_flags": [],
        "explanation": "",
        "actions": []
    }
    try:
        data.update(json.loads(raw))
    except Exception:
        try:
            s, e = raw.find("{"), raw.rfind("}")
            if s != -1 and e != -1 and e > s:
                data.update(json.loads(raw[s:e+1]))
        except Exception:
            data["explanation"] = "Resposta do LLM não estava em JSON; assumindo OK."

    data["label"] = (data.get("label") or "ok").lower()
    if data["label"] not in ("ok","suspeito","fraude"):
        data["label"] = "ok"
    try:
        data["risk_score_llm"] = max(0.0, min(1.0, float(data.get("risk_score_llm", 0.0))))
        data["confidence_llm"] = max(0.0, min(1.0, float(data.get("confidence_llm", 0.0))))
    except Exception:
        data["risk_score_llm"], data["confidence_llm"] = 0.2, 0.4
    data["red_flags"] = data.get("red_flags") or []
    data["actions"] = data.get("actions") or []
    data["explanation"] = data.get("explanation") or ""

    # Suavizador para casos legítimos — não interfere nos de impersonation crítico
    try:
        if signals.get("domain_whitelisted") and signals.get("https_2xx_no_chain") and not re.search(r"(senha|token|c[oó]digo|pix|documento|selfie)", signals["content_excerpt"], re.I):
            data["risk_score_llm"] = max(0.0, min(1.0, data["risk_score_llm"] * 0.7))
            if data["risk_score_llm"] < 0.4 and data["label"] != "fraude":
                data["label"] = "ok"
    except Exception:
        pass

    return data
