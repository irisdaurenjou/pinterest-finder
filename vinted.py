import requests

VINTED_API = "https://www.vinted.fr/api/v2"

# Session partagée pour réutiliser les cookies
_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://www.vinted.fr/",
})


def _ensure_session():
    """Récupère les cookies nécessaires via une visite de la page d'accueil."""
    if not _session.cookies:
        _session.get("https://www.vinted.fr/", timeout=10)


def search(query: str, max_results: int = 6) -> list[dict]:
    _ensure_session()
    try:
        resp = _session.get(
            f"{VINTED_API}/catalog/items",
            params={
                "search_text": query,
                "per_page": max_results,
                "order": "relevance",
            },
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception:
        return []

    results = []
    for item in items:
        photo = item.get("photo", {})
        image_url = photo.get("url") or photo.get("thumbnails", [{}])[-1].get("url", "")
        results.append({
            "source": "Vinted",
            "title": item.get("title", ""),
            "price": f"{item.get('price', '')} {item.get('currency', '€')}",
            "url": f"https://www.vinted.fr/items/{item.get('id')}",
            "image": image_url,
            "size": item.get("size_title", ""),
            "brand": item.get("brand_title", ""),
        })
    return results
