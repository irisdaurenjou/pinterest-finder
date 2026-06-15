import os
import requests

PINTEREST_API = "https://api.pinterest.com/v5"
PINTEREST_AUTH = "https://www.pinterest.com/oauth"


def get_auth_url(redirect_uri: str, state: str) -> str:
    app_id = os.environ["PINTEREST_APP_ID"]
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "boards:read,pins:read",
        "state": state,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{PINTEREST_AUTH}/?{query}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    resp = requests.post(
        f"{PINTEREST_AUTH}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(os.environ["PINTEREST_APP_ID"], os.environ["PINTEREST_APP_SECRET"]),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_boards(access_token: str) -> list[dict]:
    boards = []
    url = f"{PINTEREST_API}/boards"
    params = {"page_size": 50}
    while url:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        boards.extend(data.get("items", []))
        bookmark = data.get("bookmark")
        if bookmark:
            params = {"page_size": 50, "bookmark": bookmark}
        else:
            url = None
    return boards


def get_pins(access_token: str, board_id: str, max_pins: int = 50) -> list[dict]:
    pins = []
    url = f"{PINTEREST_API}/boards/{board_id}/pins"
    params = {"page_size": min(max_pins, 50)}
    while url and len(pins) < max_pins:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        pins.extend(data.get("items", []))
        bookmark = data.get("bookmark")
        if bookmark and len(pins) < max_pins:
            params = {"page_size": min(max_pins - len(pins), 50), "bookmark": bookmark}
        else:
            url = None
    return pins[:max_pins]


def extract_keywords(pin: dict) -> str:
    """Construit une requête de recherche à partir des métadonnées du pin."""
    parts = []
    title = pin.get("title", "").strip()
    desc = pin.get("description", "").strip()
    if title:
        parts.append(title)
    elif desc:
        # Prend les 60 premiers caractères de la description
        parts.append(desc[:60])
    return " ".join(parts) if parts else ""
