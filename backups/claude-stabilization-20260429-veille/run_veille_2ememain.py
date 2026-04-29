import asyncio
from playwright.async_api import async_playwright
import json
import re
import os
from pathlib import Path
from urllib.parse import urlparse

# --- Validation logic ---

PRICE_FREE_PATTERN = re.compile(
    r"^\s*(?:gratis|gratuit|€\s*0(?:[,\.]00?)?|0(?:[,\.]00?)?\s*€?)\s*$",
    re.IGNORECASE,
)

NEGATIVE_TOKENS = (
    "cherche", "gezocht", "recherche", "wanted",
    "frais", "kosten",
    "enlevement payant", "enlèvement payant",
    "contre service", "echange", "échange", "troc", "ruil",
    "estimation gratuite", "consultation gratuite",
)

def is_truly_free(price_raw: str, title: str) -> tuple[bool, str]:
    if not price_raw:
        return False, "no_price_dom"

    # Match against the first line of price_raw (e.g., "Gratuit\nAujourd'hui")
    lines = price_raw.split('\n')
    first_line = lines[0].strip()
    
    if not PRICE_FREE_PATTERN.match(first_line):
        return False, f"price_not_zero:{first_line[:30]}"

    haystack = (title or "").lower()
    for token in NEGATIVE_TOKENS:
        if token in haystack:
            return False, f"negative_token:{token}"
    return True, "ok"

# --- Scraper ---

def category_from_url(url: str) -> str:
    labels = {
        "maison-meubles": "Maison / meubles",
        "electromenager": "Electromenager",
        "vetements-hommes": "Vetements",
        "informatique-logiciels": "Informatique",
        "tv-hi-fi-video": "TV / hi-fi",
        "sports-fitness": "Sport / fitness",
        "jardin-terrasse": "Jardin / terrasse",
    }
    parts = [part for part in urlparse(url).path.split("/") if part]
    slug = parts[1] if len(parts) > 1 and parts[0] == "l" else (parts[-1] if parts else "")
    return labels.get(slug, slug.replace("-", " ").title() or "Autre")

async def scrape_url(context, url):
    page = await context.new_page()
    try:
        print(f"Scraping {url}...")
        await page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(8)

        ads = await page.evaluate("""
            () => {
                const out = [];
                const items = document.querySelectorAll('li[class*="Listing"]');
                items.forEach(item => {
                    const priceEl = item.querySelector('[class*="price"], [data-test-id*="price"], [class*="Price"]');
                    const priceRaw = priceEl ? priceEl.innerText.trim() : '';
                    const titleEl = item.querySelector('h3, [class*="title"]');
                    const title = titleEl ? titleEl.innerText.trim() : '';
                    const linkEl = item.querySelector('a[href*="/v/"]');
                    const link = linkEl ? linkEl.href : null;
                    out.push({ priceRaw, title, link });
                });
                return out;
            }
        """)

        accepted = []
        category = category_from_url(url)
        for raw in ads:
            if not raw.get("link"):
                continue
            ok, reason = is_truly_free(raw.get("priceRaw", ""), raw.get("title", ""))
            if ok:
                accepted.append({
                    "title": raw["title"] or "Sans titre",
                    "price": "Gratuit",
                    "price_raw": raw.get("priceRaw", ""),
                    "link": raw["link"],
                    "category": category,
                    "source_url": url,
                })
        
        print(f"  -> scanned={len(ads)} accepted={len(accepted)}")
        await page.close()
        return accepted
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        await page.close()
        return []

async def main():
    config_path = "veille_2ememain_config.json"
    history_path = "veille_2ememain_history.json"

    if not os.path.exists(config_path):
        print(f"Config file {config_path} not found.")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
    except:
        history = []

    browser_candidates = [
        os.environ.get("NANOBOT_CHROME_EXE"),
        r"C:\Users\user\AppData\Local\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Users\user\AppData\Local\ms-playwright\chromium-1208\chrome-win64\chrome.exe",
    ]
    browser_path = next((p for p in browser_candidates if p and Path(p).is_file()), None)
    if not browser_path:
        raise FileNotFoundError("No Chrome/Chromium executable found for Playwright")

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=browser_path, headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1000},
        )

        all_new_ads = []
        seen_history = set(history)
        seen_in_run = set()

        for url in config['urls']:
            ads = await scrape_url(context, url)
            for ad in ads:
                match = re.search(r'/(m\d+)', ad['link'])
                ad_id = match.group(1) if match else ad['link']
                if ad_id in seen_history or ad_id in seen_in_run:
                    continue
                all_new_ads.append(ad)
                seen_in_run.add(ad_id)

        await browser.close()

        if all_new_ads:
            for ad in all_new_ads:
                match = re.search(r'/(m\d+)', ad['link'])
                history.append(match.group(1) if match else ad['link'])
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)

            print("---RESULTS_START---")
            print(json.dumps(all_new_ads, indent=2, ensure_ascii=False))
            print("---RESULTS_END---")
        else:
            print("Aucune nouvelle annonce.")

if __name__ == "__main__":
    asyncio.run(main())
