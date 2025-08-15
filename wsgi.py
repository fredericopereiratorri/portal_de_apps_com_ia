import os, re, glob, importlib.util, sys, contextlib
from flask import Flask, send_from_directory
from werkzeug.middleware.dispatcher import DispatcherMiddleware

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- utils ----------
def find_flask_app_file(root_dir):
    """
    Procura recursivamente um .py que exponha 'app = Flask(...)' ou 'application = Flask(...)'.
    Prioriza app.py, wsgi.py, main.py e menor profundidade.
    """
    candidates = []
    for path in glob.glob(os.path.join(root_dir, "**", "*.py"), recursive=True):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                src = f.read(200000)
        except Exception:
            continue
        if "Flask(" in src and re.search(r"\b(app|application)\s*=\s*Flask\(", src):
            score = 0
            name = os.path.basename(path).lower()
            if name == "app.py":  score += 10
            if name == "wsgi.py": score += 7
            if name == "main.py": score += 5
            depth = len(os.path.relpath(path, root_dir).split(os.sep))
            candidates.append((score, -depth, path))
    if not candidates:
        raise FileNotFoundError(f"Nenhum arquivo Flask encontrado em: {root_dir}")
    candidates.sort(reverse=True)
    return candidates[0][2]

@contextlib.contextmanager
def pushd(new_dir):
    prev_cwd = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(prev_cwd)

def load_flask_app(module_path):
    """
    Importa o módulo garantindo:
    - a pasta do app no sys.path (para 'from utils import ...', etc.)
    - cwd na pasta do app (para acessos relativos).
    Retorna 'app' ou 'application'.
    """
    module_dir = os.path.dirname(os.path.abspath(module_path))
    module_name = f"_dyn_{os.path.basename(module_path).replace('.py','')}"
    sys_path_had = module_dir in sys.path
    if not sys_path_had:
        sys.path.insert(0, module_dir)
    try:
        with pushd(module_dir):
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
    finally:
        if not sys_path_had:
            try: sys.path.remove(module_dir)
            except ValueError: pass
    app = getattr(mod, "app", None) or getattr(mod, "application", None)
    if app is None:
        raise RuntimeError(f"'{module_path}' não expõe 'app' nem 'application'.")
    return app

# ---------- portal (landing /) ----------
portal = Flask(__name__, static_folder=BASE_DIR, template_folder=BASE_DIR)

@portal.route("/")
def landing():
    return send_from_directory(BASE_DIR, "index.html")

@portal.route("/<path:path>")
def portal_static(path):
    abs_path = os.path.join(BASE_DIR, path)
    if os.path.isfile(abs_path):
        return send_from_directory(BASE_DIR, path)
    return send_from_directory(BASE_DIR, "index.html")

# ---------- montar SOMENTE o Verificador de Fraudes ----------
# Ajuste este nome se sua pasta tiver outro nome:
fraudes_root = os.path.join(BASE_DIR, "Verificador de Fraudes")
fraudes_file = find_flask_app_file(fraudes_root)
verificador_app = load_flask_app(fraudes_file)  # monta em /verificador_de_fraudes

# ---------- WSGI combinado ----------
application = DispatcherMiddleware(portal, {
    "/verificador_de_fraudes": verificador_app,
})
