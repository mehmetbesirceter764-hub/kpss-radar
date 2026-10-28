
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SOURCES = [
    ("ÖSYM duyuruları", "https://www.osym.gov.tr/"),
    ("Kariyer Kapısı", "https://kariyerkapisi.gov.tr/isealim"),
]

KEYWORDS = [
    # Eğitim düzeyi ve KPSS
    "kpss",
    "kpss p94",
    "ortaöğretim",
    "lise mezunu",

    # Memur ve sözleşmeli personel
    "memur alımı",
    "memur alımları",
    "personel alımı",
    "personel alımları",
    "kamu personeli",
    "sözleşmeli personel",
    "destek personeli",

    # Kamu işçisi
    "kamu işçisi",
    "işçi alımı",
    "sürekli işçi",
    "temizlik görevlisi",
    "şoför alımı",

    # Askerî personel
    "uzman erbaş",
    "sözleşmeli er",
    "askerî personel",
    "askeri personel",
    "jandarma alımı",

    # Polis ve güvenlik
    "polis alımı",
    "bekçi alımı",
    "koruma ve güvenlik",
    "güvenlik görevlisi",
    "zabıta alımı",
    "itfaiye eri",
]

def scan():
    items = []
    errors = []

    for source_name, url in SOURCES:
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "KPSS-Radar/1.0"}
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            for link in soup.find_all("a", href=True):
                title = " ".join(link.get_text(" ", strip=True).split())
                target = urljoin(url, link["href"])
                searchable = title.casefold()

                if title and any(word in searchable for word in KEYWORDS):
                    items.append({
                        "source": source_name,
                        "title": title,
                        "url": target,
                    })

        except Exception as exc:
            errors.append({
                "source": source_name,
                "error": str(exc),
            })

    unique = {
        item["url"]: item
        for item in items
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not errors else "partial",
        "items": list(unique.values()),
        "errors": errors,
    }

if __name__ == "__main__":
    import json
    print(json.dumps(scan(), ensure_ascii=False, indent=2))
  
