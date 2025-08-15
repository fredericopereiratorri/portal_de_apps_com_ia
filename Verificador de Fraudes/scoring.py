# scoring.py
import re

# Palavras de alto risco (se aparecem, não pode sair "OK" com risco médio)
HIGH_SEVERITY_TOKENS = (
    "sorteio", "prêmio", "premio", "ganhador", "ganhe", "parabéns", "parabens",
    "clique e participe", "clique para participar", "resgatar prêmio", "resgate",
    "receba agora", "promoção", "promocao", "vencedor",
    "confirme sua senha", "token", "pix", "atualize sua conta", "bloqueado", "suspenso"
)

def _has_any(text: str, tokens) -> bool:
    t = (text or "").lower()
    return any(tok in t for tok in tokens)

def combine_scores(heur: dict, llm: dict, meta: dict = None, source_type: str = "", raw_text: str = "") -> dict:
    """
    Combina heurística e LLM em um único veredito, com limiares corrigidos:
      - FRAUDE: risk >= 0.60  ou (heurística muito alta ou sinais gravíssimos)
      - SUSPEITO: 0.35 <= risk < 0.60  ou presença de tokens de alto risco
      - OK: risk < 0.35 e sem tokens de alto risco
    Também aplica boosts/penalidades leves dependendo do contexto.
    """
    meta = meta or {}
    h_score = float(heur.get("score", 0.0))
    l_risk = float(llm.get("risk_score_llm", 0.0))
    l_conf = float(llm.get("confidence_llm", 0.0))

    # Combinação simples com pesos
    # (ajuste: dê mais peso à heurística quando houver sinais claros no conteúdo)
    base_risk = 0.55 * h_score + 0.45 * l_risk

    # Boost por sinais graves no texto bruto
    if _has_any(raw_text, HIGH_SEVERITY_TOKENS):
        base_risk += 0.08

    # Boost por impersonation não-crítica detectada
    if meta.get("brand_impersonation_detected"):
        base_risk += 0.06

    # Cap nos limites [0, 1]
    base_risk = max(0.0, min(1.0, base_risk))

    # Confiança combinada: média ponderada (LLM mais confiável)
    confidence = 0.6 * l_conf + 0.4 * (1.0 - abs(h_score - l_risk))

    # Regras de rótulo (CORRIGIDAS)
    # NUNCA retornar "OK" quando base_risk >= 0.35 ou quando houver tokens graves
    has_high_sev = _has_any(raw_text, HIGH_SEVERITY_TOKENS)
    if base_risk >= 0.60:
        label = "fraude"
    elif base_risk >= 0.35 or has_high_sev:
        label = "suspeito"
    else:
        label = "ok"

    # Ações recomendadas padrão (podem ser sobrescritas por llm)
    actions = []
    if label == "fraude":
        actions = [
            "Não clique em links nem abra anexos.",
            "Não responda ao remetente.",
            "Reporte ao time de segurança/abuse do provedor.",
            "Se forneceu dados, troque senhas e monitore contas."
        ]
    elif label == "suspeito":
        actions = [
            "Desconfie: valide no site/app oficial.",
            "Evite clicar até confirmar a legitimidade.",
            "Cheque remetente/domínio e ortografia.",
        ]

    return {
        "risk": base_risk,
        "confidence": max(0.0, min(1.0, confidence)),
        "label": label,
        "actions": actions
    }
