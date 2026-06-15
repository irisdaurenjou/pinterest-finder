import os
import json
import zipfile
import secrets
import concurrent.futures
from functools import wraps
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


def parse_pinterest_export(zip_file) -> list[dict]:
    boards = {}

    with zipfile.ZipFile(zip_file) as zf:
        names = zf.namelist()

        pins_file = next((n for n in names if n.endswith("pins.json")), None)
        boards_file = next((n for n in names if n.endswith("boards.json")), None)

        board_names = {}
        if boards_file:
            with zf.open(boards_file) as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    for b in raw:
                        board_names[str(b.get("id", ""))] = b.get("name", "Tableau")
                elif isinstance(raw, dict):
                    for bid, b in raw.items():
                        board_names[str(bid)] = b.get("name", "Tableau") if isinstance(b, dict) else str(b)

        if pins_file:
            with zf.open(pins_file) as f:
                raw = json.load(f)
                pins = raw if isinstance(raw, list) else raw.get("pins", [])

            for pin in pins:
                board_id = str(pin.get("board_id") or pin.get("board", {}).get("id", "inconnu"))
                board_name = board_names.get(board_id) or pin.get("board", {}).get("name", "Tableau")

                if board_id not in boards:
                    boards[board_id] = {"id": board_id, "name": board_name, "pins": []}

                media = pin.get("media") or {}
                images = media.get("images") or {}
                image_url = ""
                for size in ("400x300", "236x", "orig"):
                    if size in images:
                        image_url = images[size].get("url", "")
                        break
                if not image_url and isinstance(images, dict):
                    for v in images.values():
                        if isinstance(v, dict) and v.get("url"):
                            image_url = v["url"]
                            break

                boards[board_id]["pins"].append({
                    "id": pin.get("id", ""),
                    "title": pin.get("title", "").strip(),
                    "description": pin.get("description", "").strip(),
                    "image": image_url,
                })

    return list(boards.values())


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
                boards = parse_pinterest_export(f)
                session["boards"] = boards
            except Exception as e:
                error = f"Impossible de lire le fichier : {e}"
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
