
import re
import json
from datetime import datetime, timezone
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

SOURCES = [
    ("ÖSYM duyuruları", "https://www.osym.gov.tr/"),
    ("Kariyer Kapısı", "https://kariyerkapisi.gov.tr/isealim"),
]

KEYWORDS = [
    "kpss", "ortaöğretim", "lise mezunu",
    "memur alımı", "personel alımı", "personel alımları",
    "sözleşmeli personel", "destek personeli",
    "kamu işçisi", "işçi alımı", "sürekli işçi",
    "temizlik görevlisi", "şoför alımı",
    "uzman erbaş", "sözleşmeli er",
    "askerî personel", "askeri personel",
    "jandarma alımı", "polis alımı", "bekçi alımı",
    "koruma ve güvenlik", "güvenlik görevlisi",
    "zabıta alımı", "itfaiye eri",
]

DATE_PATTERN = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; KPSS-Radar/1.0)"
    )
}

TIMEOUT = 20
MAX_DETAIL_PAGES = 25


def normalize(text):
    return " ".join(text.casefold().split())


def get_page(session, url):
    response = session.get(
        url,
        timeout=TIMEOUT,
        headers=HEADERS,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def extract_dates(text):
    return list(dict.fromkeys(DATE_PATTERN.findall(text)))


def scan():
    items = []
    errors = []
    seen_urls = set()
    session = requests.Session()

    for source_name, source_url in SOURCES:
        try:
            soup = get_page(session, source_url)
            candidates = []

            for link in soup.find_all("a", href=True):
                title = " ".join(
                    link.get_text(" ", strip=True).split()
                )
                target = urldefrag(
                    urljoin(source_url, link["href"])
                ).url

                parsed = urlparse(target)

                if not title or parsed.scheme not in ("http", "https"):
                    continue

                if parsed.netloc != urlparse(source_url).netloc:
                    continue

                searchable = normalize(title + " " + target)

                if any(word in searchable for word in KEYWORDS):
                    candidates.append((title, target))

            # Ana sayfada bulunan aday bağlantıları incele.
            for title, target in candidates[:MAX_DETAIL_PAGES]:
                if target in seen_urls:
                    continue

                seen_urls.add(target)

                try:
                    detail = get_page(session, target)

                    for tag in detail(
                        ["script", "style", "nav", "footer", "header"]
                    ):
                        tag.decompose()

                    page_title = (
                        detail.title.get_text(" ", strip=True)
                        if detail.title else title
                    )
                    body = detail.get_text(" ", strip=True)
                    body = " ".join(body.split())
                    searchable_body = normalize(
                        page_title + " " + body
                    )

                    if not any(
                        word in searchable_body
                        for word in KEYWORDS
                    ):
                        continue

                    has_high_school = any(
                        phrase in searchable_body
                        for phrase in (
                            "ortaöğretim",
                            "lise mezunu",
                            "lise ve dengi",
                            "orta öğretim",
                        )
                    )

                    has_kpss = "kpss" in searchable_body
                    dates = extract_dates(body)

                    items.append({
                        "source": source_name,
                        "title": page_title or title,
                        "url": target,
                        "education_match": (
                            "possible" if has_high_school
                            else "not_confirmed"
                        ),
                        "kpss_mentioned": has_kpss,
                        "dates_found": dates,
                        "verification": "manual_review_required",
                        "snippet": body[:500],
                    })

                except Exception as exc:
                    errors.append({
                        "source": source_name,
                        "url": target,
                        "error": str(exc),
                    })

        except Exception as exc:
            errors.append({
                "source": source_name,
                "error": str(exc),
            })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": (
            "ok" if not errors
            else "partial" if items
            else "error"
        ),
        "items": items,
        "errors": errors,
    }


if __name__ == "__main__":
    print(json.dumps(scan(), ensure_ascii=False, indent=2))
    
