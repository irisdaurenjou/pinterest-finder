import requests
from bs4 import BeautifulSoup

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

LBC_SEARCH = "https://www.leboncoin.fr/recherche"


def search(query: str, max_results: int = 6) -> list[dict]:
    try:
        resp = _session.get(
            LBC_SEARCH,
            params={"text": query, "locations": ""},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception:
        return []

    results = []
    # Les annonces sont dans des balises <a> avec data-qa-id="aditem_container"
    ads = soup.select("a[data-qa-id='aditem_container']")
    for ad in ads[:max_results]:
        title_el = ad.select_one("[data-qa-id='aditem_title']")
        price_el = ad.select_one("[data-qa-id='aditem_price']")
        img_el = ad.select_one("img")
        link = ad.get("href", "")
        if not link.startswith("http"):
            link = "https://www.leboncoin.fr" + link
        results.append({
            "source": "Leboncoin",
            "title": title_el.get_text(strip=True) if title_el else "",
            "price": price_el.get_text(strip=True) if price_el else "",
            "url": link,
            "image": img_el.get("src", "") if img_el else "",
            "size": "",
            "brand": "",
        })

    return results
