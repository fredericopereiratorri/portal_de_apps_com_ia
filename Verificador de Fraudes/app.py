import io
import os
import json
import time
import hashlib
import threading
import mimetypes
import traceback
from flask import Flask, render_template, request
from markupsafe import Markup
from dotenv import load_dotenv

load_dotenv()

from utils import safe_html_snippet
from validators import is_allowed_file, is_url
from extractors import extract_text_from_url, extract_text_from_eml
from ocr import ocr_from_image_file
from heuristics import heuristic_score
from scoring import combine_scores
from llm_client import llm_analyze
from brand_guard import detect_brand_impersonation

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10")) * 1024 * 1024

DEV_NO_CACHE = os.getenv("DEV_NO_CACHE", "0") == "1" or os.getenv("FLASK_ENV") == "development"
if DEV_NO_CACHE:
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    @app.after_request
    def add_no_cache_headers(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

@app.context_processor
def inject_cache_bust():
    return {"cache_bust": int(time.time()) if DEV_NO_CACHE else ""}

FG_DEBUG = os.getenv("FG_DEBUG", "0") == "1"

# -------------------- Cache em memória --------------------
class TTLCache:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()
    def get(self, key):
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            exp, value = item
            if exp is not None and exp < now:
                self._data.pop(key, None)
                return None
            return value
    def setex(self, key, ttl_seconds, value):
        exp = time.time() + ttl_seconds if ttl_seconds else None
        with self._lock:
            self._data[key] = (exp, value)

_cache = TTLCache()
def cache_get(k): return _cache.get(k)
def cache_set(k, v, ttl=3600): _cache.setex(k, ttl, v)

# -------------------- Whitelist simples --------------------
SAFEBOOK = "safebook.json"
_safe = {"domains": [], "phrases": []}
_safe_lock = threading.Lock()

def load_safebook():
    global _safe
    if os.path.exists(SAFEBOOK):
        try:
            _safe = json.load(open(SAFEBOOK, "r", encoding="utf-8"))
        except Exception:
            _safe = {"domains": [], "phrases": []}

def save_safebook():
    with _safe_lock:
        json.dump(_safe, open(SAFEBOOK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

load_safebook()

@app.post("/whitelist")
def whitelist():
    item = (request.form.get("item") or "").strip()
    typ  = (request.form.get("type") or "domain").strip()
    if not item:
        return {"ok": False, "error": "item vazio"}, 400
    with _safe_lock:
        _safe.setdefault("domains", [])
        _safe.setdefault("phrases", [])
        if typ == "domain" and item not in _safe["domains"]:
            _safe["domains"].append(item)
        elif typ == "phrase" and item not in _safe["phrases"]:
            _safe["phrases"].append(item)
        else:
            return {"ok": False, "error": "tipo inválido"}, 400
        save_safebook()
    return {"ok": True}

# -------------------- Gatilhos para imagem phishing visual --------------------
_PRIZE_CTA_ANY = (
    "sorteio", "prêmio", "premio", "ganhe", "ganhador", "parabéns", "parabens",
    "clique e participe", "clique para participar", "resgatar prêmio", "resgate",
    "receba agora", "participe", "promoção", "promocao", "vencedor"
)

# Palavras de marcas comuns (fallback mesmo sem brand_guard)
_BRAND_WORDS = (
    "banco do brasil", "bancodobrasil", "bb ",
    "bradesco", "itau", "itaú", "santander", "caixa", "nubank",
    "tim", "claro", "vivo", "oi"
)

def _has_prize_cta(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in _PRIZE_CTA_ANY)

def _has_brand_words(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in _BRAND_WORDS)

# -------------------- Rotas --------------------
@app.get("/")
def index():
    return render_template("index.html")

@app.post("/analyze")
def analyze():
    source_text = (request.form.get("input_text") or "").strip()
    source_url  = (request.form.get("input_url")  or "").strip()
    file = request.files.get("input_file")

    content, source_type, meta = "", None, {}

    try:
        # TEXTO
        if source_text:
            content, source_type = source_text, "text"
            meta["source_type"] = "text"

        # URL
        elif source_url and is_url(source_url):
            source_type = "url"; meta["source_type"] = "url"
            cache_key = "url:" + hashlib.sha256(source_url.encode()).hexdigest()
            cached = cache_get(cache_key)
            if cached:
                content = cached["content"]; meta.update(cached.get("meta", {}) or {})
            else:
                content, url_meta = extract_text_from_url(source_url)
                meta.update(url_meta or {})
                cache_set(cache_key, {"content": content, "meta": meta}, ttl=21600)

        # ARQUIVO (imagem/.eml)
        elif file and file.filename:
            filename = file.filename
            raw = file.read(); file.seek(0)
            if not is_allowed_file(filename):
                return render_template("result.html", error="Tipo de arquivo não permitido.", meta={}, content="", llm="")
            ext  = (os.path.splitext(filename)[1] or "").lower()
            mime = mimetypes.guess_type(filename)[0] or ""
            h    = hashlib.sha256(raw).hexdigest()

            if ext in [".png",".jpg",".jpeg",".webp",".bmp"] or (mime and mime.startswith("image/")):
                source_type = "image"; meta["source_type"] = "image"
                cache_key = "img:" + h
                cached = cache_get(cache_key)
                if cached:
                    content = cached["content"]; meta.update(cached.get("meta", {}) or {})
                else:
                    result = ocr_from_image_file(io.BytesIO(raw))
                    if isinstance(result, tuple): content, dbg = result; meta["ocr_debug"] = dbg
                    else: content = result
                    cache_set(cache_key, {"content": content, "meta": {"ocr_debug": meta.get("ocr_debug")}}, ttl=86400)
                meta["ocr_text_len"] = len(content or "")
                if not (content or "").strip():
                    hint = ("OCR executou, mas não encontrou texto na imagem.\n\n"
                            "Tente:\n- Usar imagem com maior resolução/contraste\n- Evitar fotos tortas (perspectiva)\n"
                            "- Incluir letras maiores\n- Ajustar idiomas (OCR_LANG=por+eng no .env)\n- Ativar debug (OCR_DEBUG=1)")
                    return render_template("result.html", error=hint, meta=meta, content="", llm="",
                                           snippet=Markup("<pre class='snippet'>(sem texto OCR)</pre>"),
                                           label="suspeito", risk_pct=35.0, conf_pct=40.0,
                                           red_flags=["Imagem sem texto reconhecível pelo OCR."],
                                           actions=["Reenvie uma imagem mais nítida.", "Verifique o idioma do Tesseract (por)."])

            elif ext == ".eml":
                source_type = "email"; meta["source_type"] = "email"
                cache_key = "eml:" + h
                cached = cache_get(cache_key)
                if cached:
                    content = cached["content"]; meta.update(cached.get("meta", {}) or {})
                else:
                    content, eml_meta = extract_text_from_eml(io.BytesIO(raw))
                    meta.update(eml_meta or {})
                    cache_set(cache_key, {"content": content, "meta": meta}, ttl=86400)
            else:
                return render_template("result.html", error="Arquivo não suportado.", meta={}, content="", llm="")
        else:
            return render_template("result.html", error="Informe um texto, URL, imagem ou arquivo .eml.", meta={}, content="", llm="")

        if not (content or "").strip():
            return render_template("result.html", error="Não foi possível extrair conteúdo para análise.", meta=meta, content="", llm="")

        # Whitelist
        domain_source = (meta.get("final_url") or meta.get("url") or "").lower()
        for d in (_safe.get("domains") or []):
            if d and domain_source.endswith(d.lower()):
                meta["domain_whitelisted"] = True; break
        text_lower = (content or "").lower()
        for p in (_safe.get("phrases") or []):
            if p and p.lower() in text_lower:
                meta["phrase_whitelisted"] = True; break

        # Impersonation (e-mail/URL)
        imp = detect_brand_impersonation(meta, content)
        meta["brand_impersonation_detected"] = bool(imp.get("detected"))
        if imp.get("reason"): meta["brand_impersonation_reason"] = imp["reason"]

        if FG_DEBUG:
            print("[FG_DEBUG] From:", meta.get("from"))
            print("[FG_DEBUG] From registered:", meta.get("from_registered_domain"))
            print("[FG_DEBUG] Subject:", meta.get("subject"))
            print("[FG_DEBUG] Brand check:", imp)

        if imp.get("critical_impersonation"):
            label = "fraude"; risk_pct = 95.0; conf_pct = 90.0
            red_flags = [imp.get("reason") or "Impersonation de marca detectado."]
            actions = [
                "Não clique em nenhum link.",
                "Não responda ao e-mail.",
                "Reporte ao time de segurança/abuse do provedor.",
                "Se informou dados, altere senhas e contate o suporte oficial."
            ]
            snippet = safe_html_snippet(content)
            return render_template("result.html",
                source_type=source_type, snippet=Markup(snippet),
                label=label, risk_pct=risk_pct, conf_pct=conf_pct,
                red_flags=red_flags, actions=actions, meta=meta, content=content,
                explanation="Fraude confirmada por impersonation de marca (regra crítica).", benign_notes=[]
            )

        # NOVO: Regra determinística para IMAGEM (phishing visual)
        # Marca (por palavras comuns) + prêmio/sorteio/CTA ⇒ FRAUDE
        if source_type == "image" and _has_prize_cta(content) and (_has_brand_words(content) or meta.get("brand_impersonation_detected")):
            label = "fraude"; risk_pct = 92.0; conf_pct = 82.0
            reason = meta.get("brand_impersonation_reason") or "Marca mencionada na arte."
            red_flags = [
                reason,
                "Imagem contém gatilhos de prêmio/sorteio/CTA.",
                "Phishing visual sem comprovação de domínio oficial."
            ]
            actions = [
                "Não acesse links ou QR codes desse material.",
                "Verifique campanhas no site/app oficial da marca.",
                "Reporte este conteúdo ao time de segurança."
            ]
            snippet = safe_html_snippet(content)
            return render_template("result.html",
                source_type=source_type, snippet=Markup(snippet),
                label=label, risk_pct=risk_pct, conf_pct=conf_pct,
                red_flags=red_flags, actions=actions, meta=meta, content=content,
                explanation="Fraude por phishing visual (marca + prêmio/sorteio/CTA detectados).", benign_notes=[]
            )

        # Heurística → LLM → Combinação
        heur = heuristic_score(content, meta)

        content_hash = hashlib.sha256((meta.get("source_type","") + "|" + content[:20000]).encode("utf-8","ignore")).hexdigest()
        cache_key_llm = "llm:" + content_hash
        cached_llm = cache_get(cache_key_llm)
        if cached_llm: llm = cached_llm
        else:
            llm = llm_analyze(content, meta)
            cache_set(cache_key_llm, llm, ttl=43200)

        final = combine_scores(heur, llm, meta=meta, source_type=source_type, raw_text=content)
        label = final["label"]; risk_pct = round(final["risk"]*100, 1); conf_pct = round(final["confidence"]*100, 1)

        red_flags = (llm.get("red_flags") or []) + (heur.get("red_flags") or [])
        seen = set(); red_flags = [x for x in red_flags if not (x in seen or seen.add(x))]
        benign_notes = heur.get("benign_notes") or []
        actions = final.get("actions") or llm.get("actions") or []
        explanation = llm.get("explanation", "")
        snippet = safe_html_snippet(content)

        return render_template("result.html",
            source_type=source_type, snippet=Markup(snippet),
            label=label, risk_pct=risk_pct, conf_pct=conf_pct,
            red_flags=red_flags[:12], actions=actions[:10],
            meta=meta, content=content, explanation=explanation, benign_notes=benign_notes, llm=""
        )

    except Exception as e:
        print("Erro:\n", traceback.format_exc())
        return render_template("result.html", error=f"Falha na análise: {e}", meta={}, content="", llm="")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
