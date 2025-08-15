# ocr.py
import os
import re
import time
import numpy as np
import pytesseract
from PIL import Image, ImageOps, ImageFilter

try:
    import cv2
except Exception:
    cv2 = None  # roda sem OpenCV (com menos variações)

# Descoberta do Tesseract
_tess_env = os.getenv("TESSERACT_CMD")
if _tess_env and os.path.exists(_tess_env):
    pytesseract.pytesseract.tesseract_cmd = _tess_env
else:
    for guess in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if os.path.exists(guess):
            pytesseract.pytesseract.tesseract_cmd = guess
            break

# Infere TESSDATA_PREFIX se não existir
if not os.getenv("TESSDATA_PREFIX"):
    try:
        _exe = pytesseract.pytesseract.tesseract_cmd
        if _exe and os.path.exists(_exe):
            _guess = os.path.join(os.path.dirname(_exe), "tessdata")
            if os.path.isdir(_guess):
                os.environ["TESSDATA_PREFIX"] = _guess
    except Exception:
        pass

# Idiomas disponíveis
def _available_langs_from_fs():
    td = os.environ.get("TESSDATA_PREFIX")
    langs = set()
    if td and os.path.isdir(td):
        for name in os.listdir(td):
            if name.endswith(".traineddata"):
                langs.add(name[:-12])
    return langs

_av = _available_langs_from_fs()
if ("por" in _av) and ("eng" in _av):
    DEF_LANG = "por+eng"
elif "por" in _av:
    DEF_LANG = "por"
elif "eng" in _av:
    DEF_LANG = "eng"
else:
    DEF_LANG = os.getenv("OCR_LANG", "por+eng")

# Parâmetros
OCR_MODE = os.getenv("OCR_MODE", "FAST").strip().upper()  # FAST | AGGRESSIVE
TIME_BUDGET_MS = int(os.getenv("OCR_TIME_BUDGET_MS", "2200"))
EARLY_CONF_THRESHOLD = float(os.getenv("OCR_EARLY_CONF", "70.0"))
EARLY_MIN_CHARS = int(os.getenv("OCR_EARLY_MIN_CHARS", "10"))
UPSCALE = float(os.getenv("OCR_UPSCALE", "2.0"))

PSMS_FAST = [6, 11]
PSMS_FULL = [6, 11, 3, 7, 8, 4, 13]
DEBUG = os.getenv("OCR_DEBUG", "0") == "1"
WHITELIST = os.getenv("OCR_WHITELIST", "")

DEBUG_DIR = os.path.join("static", "ocr_debug")
if DEBUG:
    os.makedirs(DEBUG_DIR, exist_ok=True)

def _save_debug(img_pil, tag):
    if not DEBUG:
        return None
    ts = int(time.time() * 1000)
    name = f"dbg_{ts}_{tag}.png"
    path = os.path.join(DEBUG_DIR, name)
    img_pil.save(path, format="PNG")
    return f"/static/ocr_debug/{name}"

def _mean_conf_from_data(data_str: str) -> float:
    if not data_str:
        return -1.0
    vals = []
    for line in data_str.splitlines():
        parts = line.split("\t")
        if len(parts) > 10:
            try:
                conf = float(parts[10])
                if conf >= 0:
                    vals.append(conf)
            except Exception:
                pass
    return float(sum(vals) / len(vals)) if vals else -1.0

def _post_clean_text(txt: str) -> str:
    txt = re.sub(r"[ \t]+", " ", txt or "")
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()

def _pil_to_cv(img_pil):
    arr = np.array(img_pil)
    if arr.ndim == 2:
        return arr
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def _cv_to_pil(img_cv):
    if len(img_cv.shape) == 2:
        return Image.fromarray(img_cv)
    return Image.fromarray(cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB))

def _unsharp(img_pil):
    return img_pil.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))

def _variants_fast(img_pil):
    out = []
    if cv2 is None:
        g = ImageOps.grayscale(img_pil); g = ImageOps.autocontrast(g)
        if UPSCALE and UPSCALE != 1.0:
            g = g.resize((int(g.width*UPSCALE), int(g.height*UPSCALE)), Image.BICUBIC)
        out.append(("fast_bin170", g.point(lambda p: 255 if p > 170 else 0)))
        out.append(("fast_inv", ImageOps.invert(g)))
        out.append(("fast_gray_sharp", _unsharp(g)))
        return out

    cv_bgr = _pil_to_cv(img_pil)
    h, w = cv_bgr.shape[:2]
    if UPSCALE and UPSCALE != 1.0:
        cv_bgr = cv2.resize(cv_bgr, (int(w*UPSCALE), int(h*UPSCALE)), interpolation=cv2.INTER_CUBIC)

    hsv = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8,8))
    base = clahe.apply(v)

    _, otsu = cv2.threshold(base, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, otsu_i = cv2.threshold(base, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    out.append(("fast_v_otsu", _cv_to_pil(otsu)))
    out.append(("fast_v_otsu_inv", _cv_to_pil(otsu_i)))
    out.append(("fast_v_gray_sharp", _unsharp(_cv_to_pil(base).convert("L"))))
    return out

def _variants_full(img_pil):
    out = []
    if cv2 is None:
        g = ImageOps.grayscale(img_pil); g = ImageOps.autocontrast(g)
        if UPSCALE and UPSCALE != 1.0:
            g = g.resize((int(g.width*UPSCALE), int(g.height*UPSCALE)), Image.BICUBIC)
        for thr in (170, 150, 130):
            out.append((f"pil_bin{thr}", g.point(lambda p, t=thr: 255 if p > t else 0)))
        out.append(("pil_inv", ImageOps.invert(g)))
        out.append(("pil_gray_sharp", _unsharp(g)))
        return out

    cv_bgr = _pil_to_cv(img_pil)
    h, w = cv_bgr.shape[:2]
    if UPSCALE and UPSCALE != 1.0:
        cv_bgr = cv2.resize(cv_bgr, (int(w*UPSCALE), int(h*UPSCALE)), interpolation=cv2.INTER_CUBIC)

    b, g, r = cv2.split(cv_bgr)
    hsv = cv2.cvtColor(cv_bgr, cv2.COLOR_BGR2HSV)
    v = hsv[:, :, 2]
    channels = [("r", r), ("g", g), ("b", b), ("v", v)]
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8,8))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))

    for cname, ch in channels:
        base = clahe.apply(ch)
        toph = cv2.morphologyEx(base, cv2.MORPH_TOPHAT, kernel)
        blkh = cv2.morphologyEx(base, cv2.MORPH_BLACKHAT, kernel)

        mats = [(f"{cname}_clahe", base), (f"{cname}_tophat", toph), (f"{cname}_blackhat", blkh)]
        for tag, mat in mats:
            _, otsu = cv2.threshold(mat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            out.append((f"{tag}_otsu", _cv_to_pil(otsu)))
            _, otsu_i = cv2.threshold(mat, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            out.append((f"{tag}_otsu_inv", _cv_to_pil(otsu_i)))
            adap = cv2.adaptiveThreshold(mat, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                         cv2.THRESH_BINARY, 31, 9)
            out.append((f"{tag}_adap31", _cv_to_pil(adap)))
            adap_i = cv2.adaptiveThreshold(mat, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 31, 9)
            out.append((f"{tag}_adap31_inv", _cv_to_pil(adap_i)))
        out.append((f"{cname}_gray_sharp", _unsharp(_cv_to_pil(base).convert("L"))))

    return out

def _run_tesseract(img_pil, lang, psm, use_whitelist=False):
    cfg = f"--oem 3 --psm {psm}"
    if use_whitelist and WHITELIST:
        cfg += f' -c tessedit_char_whitelist="{WHITELIST}"'
    text = pytesseract.image_to_string(img_pil, lang=lang, config=cfg)
    data = pytesseract.image_to_data(img_pil, lang=lang, config=cfg, output_type=pytesseract.Output.STRING)
    conf = _mean_conf_from_data(data)
    return _post_clean_text(text), conf, cfg

def ocr_from_image_file(filelike, lang_env="OCR_LANG"):
    lang = os.getenv(lang_env, DEF_LANG)
    start = time.time()

    img = Image.open(filelike)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    variants = _variants_fast(img) if OCR_MODE == "FAST" else _variants_full(img)
    psms = PSMS_FAST if OCR_MODE == "FAST" else PSMS_FULL

    debug_paths = []
    best = None  # (text, conf)

    for tag, im in variants:
        pth = _save_debug(im, tag)
        if pth: debug_paths.append(pth)

        # sem whitelist
        for psm in psms:
            txt, conf, _ = _run_tesseract(im, lang=lang, psm=psm, use_whitelist=False)
            if txt:
                if best is None or conf > best[1]:
                    best = (txt, conf)
                if conf >= EARLY_CONF_THRESHOLD and len(txt) >= EARLY_MIN_CHARS:
                    return (txt, debug_paths) if DEBUG else txt
            if (time.time() - start) * 1000.0 > TIME_BUDGET_MS:
                return ((best[0] if best else ""), debug_paths) if DEBUG else (best[0] if best else "")

        # com whitelist
        if WHITELIST:
            wl_psms = ([6] if OCR_MODE == "FAST" else psms)
            for psm in wl_psms:
                txt, conf, _ = _run_tesseract(im, lang=lang, psm=psm, use_whitelist=True)
                if txt:
                    conf_b = conf + 2.0
                    if best is None or conf_b > best[1]:
                        best = (txt, conf_b)
                    if conf_b >= EARLY_CONF_THRESHOLD and len(txt) >= EARLY_MIN_CHARS:
                        return (txt, debug_paths) if DEBUG else txt
                if (time.time() - start) * 1000.0 > TIME_BUDGET_MS:
                    return ((best[0] if best else ""), debug_paths) if DEBUG else (best[0] if best else "")

    if best is None:
        base = ImageOps.grayscale(img)
        base = ImageOps.autocontrast(base)
        pth = _save_debug(base, "fallback_gray")
        if pth: debug_paths.append(pth)
        try:
            txt, conf, _ = _run_tesseract(base, lang=lang, psm=6, use_whitelist=bool(WHITELIST))
            if txt:
                best = (txt, conf)
        except Exception:
            pass

    if DEBUG:
        return (best[0] if best else "", debug_paths)
    return best[0] if best else ""
