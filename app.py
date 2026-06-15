import os
import json
import re
import zipfile
import secrets
import concurrent.futures
from functools import wraps
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup
from flask import Flask, redirect, request, session, render_template, url_for
from flask_session import Session
from dotenv import load_dotenv
import vinted
import leboncoin

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "/tmp/flask_sessions"
app.config["SESSION_PERMANENT"] = False
Session(app)

ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "")


def require_password(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if ACCESS_PASSWORD and not session.get("authenticated"):
            return redirect(url_for("password_gate", next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.route("/acces", methods=["GET", "POST"])
def password_gate():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ACCESS_PASSWORD:
            session["authenticated"] = True
            return redirect(request.args.get("next", "/"))
        error = "Mot de passe incorrect."
    return render_template("password.html", error=error)


def _slug_to_keywords(url: str) -> str:
    try:
        path = unquote(urlparse(url).path)
        # Dernier segment non vide
        segments = [s for s in path.split("/") if s and not s.isdigit() and len(s) > 3]
        if not segments:
            return ""
        slug = segments[-1]
        # Retire les extensions et remplace les séparateurs
        slug = slug.rsplit(".", 1)[0]
        words = slug.replace("-", " ").replace("_", " ").replace("+", " ")
        # Filtre les tokens purement numériques
        words = " ".join(w for w in words.split() if not w.isdigit())
        return words[:80]
    except Exception:
        return ""


def _hash_to_image(h: str) -> str:
    if not h or len(h) < 6:
        return ""
    return f"https://i.pinimg.com/236x/{h[:2]}/{h[2:4]}/{h[4:6]}/{h}.jpg"


def _parse_field(block: str, field: str) -> str:
    """Extrait la valeur d'un champ 'Field: value <br>' dans un bloc HTML."""
    # Arrête dès le premier <br (avec ou sans /)
    pattern = rf"{re.escape(field)}:\s*(.*?)\s*<br"
    m = re.search(pattern, block, re.IGNORECASE)
    if not m:
        return ""
    val = BeautifulSoup(m.group(1), "html.parser").get_text(strip=True)
    return "" if val.lower() in ("no data", "none", "") else val


def parse_pinterest_export(zip_file) -> tuple[list[dict], list[str]]:
    boards: dict = {}

    with zipfile.ZipFile(zip_file) as zf:
        names = zf.namelist()
        html_files = [n for n in names if n.endswith(".html")]

        # --- Lis tous les fichiers pins/XXXX.html ---
        pin_files = sorted(n for n in names if re.match(r"pins/\d+\.html", n))
        if not pin_files:
            return [], html_files

        for pf in pin_files:
            with zf.open(pf) as f:
                soup = BeautifulSoup(f.read(), "html.parser")

            contents = soup.find(id="contents")
            if not contents:
                continue

            # Chaque pin commence par une balise <a> avec l'URL Pinterest
            raw_html = str(contents)
            # Sépare par les liens Pinterest
            blocks = re.split(r'(?=<a href="https://www\.pinterest\.com/pin/)', raw_html)

            for block in blocks:
                if 'pinterest.com/pin/' not in block:
                    continue

                title = _parse_field(block, "Title")
                details = _parse_field(block, "Details")
                board_id = _parse_field(block, "Board Id") or "inconnu"
                board_name = _parse_field(block, "Board Name") or "Tableau"
                img_hash = _parse_field(block, "Image")
                alt_text = _parse_field(block, "Alt Text")

                # Canonical link
                canonical = ""
                cm = re.search(r'Canonical Link:\s*<a href="([^"]+)"', block)
                if cm:
                    canonical = cm.group(1)

                # URL Pinterest de la pin (pour afficher l'image via og:image)
                pin_url = ""
                pm = re.search(r'href="(https://www\.pinterest\.com/pin/[^"]+)"', block)
                if pm:
                    pin_url = pm.group(1)

                # Construit la requête de recherche
                keyword = title or alt_text or _slug_to_keywords(canonical) or details
                if not keyword:
                    continue

                # Image : hash Pinterest → CDN (format connu)
                image_url = _hash_to_image(img_hash) if img_hash else ""

                if board_id not in boards:
                    boards[board_id] = {"id": board_id, "name": board_name, "pins": []}
                elif board_name and board_name != "Tableau":
                    boards[board_id]["name"] = board_name

                boards[board_id]["pins"].append({
                    "id": "",
                    "title": keyword,
                    "description": details,
                    "image": image_url,
                    "canonical": canonical,
                })

    return list(boards.values()), html_files


@app.route("/", methods=["GET", "POST"])
@require_password
def index():
    error = None
    if request.method == "POST":
        f = request.files.get("zipfile")
        if not f or not f.filename.endswith(".zip"):
            error = "Merci d'uploader un fichier .zip (export Pinterest)."
        else:
            try:
                boards, json_files = parse_pinterest_export(f)
                session["boards"] = boards
            except Exception as e:
                error = f"Impossible de lire le fichier : {e}"
            else:
                if not boards:
                    error = f"Aucune épingle trouvée. Fichiers JSON dans le ZIP : {', '.join(json_files) or 'aucun'}"
                else:
                    return redirect(url_for("boards_view"))

    return render_template("index.html", error=error)


@app.route("/boards")
@require_password
def boards_view():
    boards = session.get("boards")
    if not boards:
        return redirect(url_for("index"))
    return render_template("boards.html", boards=boards)


@app.route("/pins/<board_id>")
@require_password
def pins_view(board_id: str):
    boards = session.get("boards", [])
    board = next((b for b in boards if b["id"] == board_id), None)
    if not board:
        return redirect(url_for("boards_view"))
    return render_template("pins.html", board=board)


@app.route("/search")
@require_password
def search_results():
    query = request.args.get("q", "").strip()
    pin_title = request.args.get("title", query)
    pin_image = request.args.get("image", "")
    if not query:
        return redirect(url_for("boards_view"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_vinted = executor.submit(vinted.search, query, 6)
        f_lbc = executor.submit(leboncoin.search, query, 6)
        vinted_results = f_vinted.result()
        lbc_results = f_lbc.result()

    return render_template(
        "results.html",
        query=query,
        pin_title=pin_title,
        pin_image=pin_image,
        vinted=vinted_results,
        leboncoin=lbc_results,
    )


@app.route("/reset")
@require_password
def reset():
    session.pop("boards", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
