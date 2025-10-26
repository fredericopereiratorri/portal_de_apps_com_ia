import os
import re
import glob
import sys
import importlib.util
import contextlib
import logging

from flask import Flask, send_from_directory
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -------- logging básico --------
log = logging.getLogger("portal")
if not log.handlers:
    h = logging.StreamHandler(stream=sys.stderr)
    h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    log.addHandler(h)
log.setLevel(logging.INFO)

# -------- utils --------
def find_flask_app_file(root_dir: str):
    """Procura um .py que exponha 'app = Flask(...)' ou 'application = Flask(...)'."""
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
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]

@contextlib.contextmanager
def pushd(new_dir: str):
    prev = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(prev)

def load_flask_app(module_path: str):
    """Importa o módulo garantindo sys.path/cwd e retorna 'app' ou 'application'."""
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
            try:
                sys.path.remove(module_dir)
            except ValueError:
                pass
    app = getattr(mod, "app", None) or getattr(mod, "application", None)
    if app is None:
        raise RuntimeError(f"'{module_path}' não expõe 'app' nem 'application'.")
    return app

# -------- Portal (landing /) --------
portal = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static")  # /static do portal
)

# CSS/JS/estáticos do PORTAL: sem condicional (evita 304 no portal)
@portal.route("/static/<path:filename>")
def portal_static_noconditional(filename):
    return send_from_directory(portal.static_folder, filename, conditional=False, max_age=0)

@portal.route("/")
def index():
    # Serve index.html da RAIZ
    return send_from_directory(BASE_DIR, "index.html")

# (opcional) servir arquivos soltos da raiz, se precisar
@portal.route("/root/<path:filename>")
def root_files(filename):
    return send_from_directory(BASE_DIR, filename)

# -------- localizar e montar o Verificador de Fraudes --------
def try_mount_fraudes():
    # tenta por env explícito
    env_file = os.environ.get("VERIFICADOR_APP_FILE")
    if env_file:
        file_path = env_file if os.path.isabs(env_file) else os.path.join(BASE_DIR, env_file)
        if os.path.isfile(file_path):
            log.info(f"[fraudes] usando VERIFICADOR_APP_FILE={file_path}")
            return load_flask_app(file_path)
        log.warning(f"[fraudes] VERIFICADOR_APP_FILE definido, mas não existe: {file_path}")

    env_root = os.environ.get("VERIFICADOR_APP_ROOT")
    if env_root:
        root_path = env_root if os.path.isabs(env_root) else os.path.join(BASE_DIR, env_root)
        if os.path.isdir(root_path):
            log.info(f"[fraudes] procurando app em VERIFICADOR_APP_ROOT={root_path}")
            found = find_flask_app_file(root_path)
            if found:
                log.info(f"[fraudes] encontrado: {found}")
                return load_flask_app(found)
            else:
                log.warning(f"[fraudes] nenhum arquivo Flask encontrado em: {root_path}")
        else:
            log.warning(f"[fraudes] VERIFICADOR_APP_ROOT definido, mas pasta não existe: {root_path}")

    # tenta pastas usuais
    for root in (
        os.path.join(BASE_DIR, "verificador_de_fraudes"),
        os.path.join(BASE_DIR, "Verificador de Fraudes"),
    ):
        if os.path.isdir(root):
            log.info(f"[fraudes] procurando app em: {root}")
            found = find_flask_app_file(root)
            if found:
                log.info(f"[fraudes] encontrado: {found}")
                return load_flask_app(found)

    log.warning("[fraudes] NÃO encontrado. O portal subirá sem /verificador_de_fraudes.")
    return None

fraudes_app = try_mount_fraudes()

# -------- localizar e montar o Heatmap --------
def try_mount_heatmap():
    # tenta por env explícito
    env_file = os.environ.get("HEATMAP_APP_FILE")
    if env_file:
        file_path = env_file if os.path.isabs(env_file) else os.path.join(BASE_DIR, env_file)
        if os.path.isfile(file_path):
            log.info(f"[heatmap] usando HEATMAP_APP_FILE={file_path}")
            return load_flask_app(file_path)
        log.warning(f"[heatmap] HEATMAP_APP_FILE definido, mas não existe: {file_path}")

    env_root = os.environ.get("HEATMAP_APP_ROOT")
    if env_root:
        root_path = env_root if os.path.isabs(env_root) else os.path.join(BASE_DIR, env_root)
        if os.path.isdir(root_path):
            log.info(f"[heatmap] procurando app em HEATMAP_APP_ROOT={root_path}")
            found = find_flask_app_file(root_path)
            if found:
                log.info(f"[heatmap] encontrado: {found}")
                return load_flask_app(found)
            else:
                log.warning(f"[heatmap] nenhum arquivo Flask encontrado em: {root_path}")
        else:
            log.warning(f"[heatmap] HEATMAP_APP_ROOT definido, mas pasta não existe: {root_path}")

    # tenta pastas usuais
    for root in (
        os.path.join(BASE_DIR, "heatmap"),
        os.path.join(BASE_DIR, "Heatmap"),
    ):
        if os.path.isdir(root):
            log.info(f"[heatmap] procurando app em: {root}")
            found = find_flask_app_file(root)
            if found:
                log.info(f"[heatmap] encontrado: {found}")
                return load_flask_app(found)

    log.warning("[heatmap] NÃO encontrado. O portal subirá sem /heatmap.")
    return None

heatmap_app = try_mount_heatmap()

# -------- app estático NÃO-CONDICIONAL para o verificador (elimina 304) --------
ver_static_app = None
ver_static_dir = None
if fraudes_app is not None:
    # tenta obter a pasta de estáticos do app
    ver_static_dir = getattr(fraudes_app, "static_folder", None)
    if ver_static_dir and os.path.isdir(ver_static_dir):
        ver_static_app = Flask("verificador_static_proxy", static_folder=ver_static_dir)

        @ver_static_app.route("/<path:filename>")
        def ver_static_noconditional(filename):
            # sempre 200 OK para os estáticos do verificador
            return send_from_directory(ver_static_dir, filename, conditional=False, max_age=0)

# -------- app estático NÃO-CONDICIONAL para o heatmap (elimina 304) --------
heatmap_static_app = None
heatmap_static_dir = None
if heatmap_app is not None:
    # tenta obter a pasta de estáticos do app
    heatmap_static_dir = getattr(heatmap_app, "static_folder", None)
    if heatmap_static_dir and os.path.isdir(heatmap_static_dir):
        heatmap_static_app = Flask("heatmap_static_proxy", static_folder=heatmap_static_dir)

        @heatmap_static_app.route("/<path:filename>")
        def heatmap_static_noconditional(filename):
            # sempre 200 OK para os estáticos do heatmap
            return send_from_directory(heatmap_static_dir, filename, conditional=False, max_age=0)

# -------- WSGI combinado --------
mounted = {}
if ver_static_app is not None:
    # rota mais específica para estáticos do verificador (sem 304)
    mounted["/verificador_de_fraudes/static"] = ver_static_app
if fraudes_app is not None:
    mounted["/verificador_de_fraudes"] = fraudes_app

if heatmap_static_app is not None:
    # rota mais específica para estáticos do heatmap (sem 304)
    mounted["/heatmap/static"] = heatmap_static_app
if heatmap_app is not None:
    mounted["/heatmap"] = heatmap_app

application = DispatcherMiddleware(portal, mounted)

# -------- Execução local (sem debugger/reloader) --------
if __name__ == "__main__":
    run_simple("0.0.0.0", 8000, application, use_reloader=False, use_debugger=False, threaded=True)
