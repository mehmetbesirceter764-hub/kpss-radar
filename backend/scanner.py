
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


# --------------------------------------------------
# KAYNAKLAR
# --------------------------------------------------

SOURCES = [
    ("ÖSYM duyuruları", "https://www.osym.gov.tr/"),
    ("Kariyer Kapısı", "https://kariyerkapisi.gov.tr/isealim"),
]


# --------------------------------------------------
# PERSONEL ALIMI ANAHTAR KELİMELERİ
# --------------------------------------------------

RECRUITMENT_TERMS = [
    "personel alımı",
    "personel alımları",
    "memur alımı",
    "memur alımları",
    "sözleşmeli personel alımı",
    "sözleşmeli personel",
    "kamu işçisi alımı",
    "işçi alımı",
    "sürekli işçi alımı",
    "uzman erbaş alımı",
    "sözleşmeli er alımı",
    "polis alımı",
    "bekçi alımı",
    "jandarma alımı",
    "güvenlik görevlisi alımı",
    "zabıta alımı",
    "itfaiye eri alımı",
    "personel istihdamı",
    "boş kadro",
    "kadrolu personel",
    "destek personeli alımı",
]


# --------------------------------------------------
# EĞİTİM VE KPSS KONTROLÜ
# --------------------------------------------------

EDUCATION_TERMS = [
    "ortaöğretim",
    "orta öğretim",
    "lise mezunu",
    "lise ve dengi",
    "lise veya dengi",
    "ortaöğretim mezunu",
]

KPSS_TERMS = [
    "kpss",
    "kpss p94",
    "2024-kpss",
    "2026-kpss",
    "p94 puan",
    "ortaöğretim kpss",
]


# --------------------------------------------------
# TARİH KONTROLÜ
# --------------------------------------------------

DATE_PATTERNS = [
    r"son başvuru(?: tarihi)?[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    r"başvurular(?:ın)?\s+(?:son günü|bitiş tarihi)[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    r"başvurular\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+tarihinde sona",
    r"başvurular\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+tarihine kadar",
]


# --------------------------------------------------
# AYARLAR
# --------------------------------------------------

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KPSS-Radar/1.0)"
}

TIMEOUT = 20
MAX_DETAIL_PAGES = 25


# --------------------------------------------------
# YARDIMCI FONKSİYONLAR
# --------------------------------------------------

def normalize(text):
    return " ".join(text.casefold().split())


def get_page(session, url):
    response = session.get(
        url,
        timeout=TIMEOUT,
        headers=HEADERS
    )
    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def extract_deadline(text):
    normalized = normalize(text)

    for pattern in DATE_PATTERNS:
        match = re.search(pattern, normalized)

        if match:
            return match.group(1)

    return None


def determine_status(deadline):
    if not deadline:
        return "unknown"

    try:
        parsed = datetime.strptime(
            deadline.replace("-", ".").replace("/", "."),
            "%d.%m.%Y"
        ).date()

        today = datetime.now().date()

        if parsed >= today:
            return "open"

        return "closed"

    except ValueError:
        return "unknown"


def contains_any(text, terms):
    return any(
        term in text
        for term in terms
    )


# --------------------------------------------------
# ANA TARAMA SİSTEMİ
# --------------------------------------------------

def scan():

    items = []
    errors = []
    seen_urls = set()

    session = requests.Session()

    checked_at = datetime.now(
        timezone.utc
    ).isoformat()

    for source_name, source_url in SOURCES:

        try:
            soup = get_page(
                session,
                source_url
            )

            candidates = []

            for link in soup.find_all(
                "a",
                href=True
            ):

                title = " ".join(
                    link.get_text(
                        " ",
                        strip=True
                    ).split()
                )

                target = urldefrag(
                    urljoin(
                        source_url,
                        link["href"]
                    )
                ).url

                parsed = urlparse(target)

                if not title:
                    continue

                if parsed.scheme not in (
                    "http",
                    "https"
                ):
                    continue

                if parsed.netloc != urlparse(
                    source_url
                ).netloc:
                    continue

                searchable = normalize(
                    title + " " + target
                )

                if contains_any(
                    searchable,
                    RECRUITMENT_TERMS
                ):
                    candidates.append(
                        (title, target)
                    )

            # Aynı bağlantıları temizle
            unique_candidates = {}

            for title, target in candidates:
                unique_candidates[target] = title

            for target, title in list(
                unique_candidates.items()
            )[:MAX_DETAIL_PAGES]:

                if target in seen_urls:
                    continue

                seen_urls.add(target)

                try:
                    detail = get_page(
                        session,
                        target
                    )

                    for tag in detail.find_all(
                        [
                            "script",
                            "style",
                            "nav",
                            "footer",
                            "header"
                        ]
                    ):
                        tag.decompose()

                    page_title = (
                        detail.title.get_text(
                            " ",
                            strip=True
                        )
                        if detail.title
                        else title
                    )

                    body = " ".join(
                        detail.get_text(
                            " ",
                            strip=True
                        ).split()
                    )

                    searchable = normalize(
                        page_title + " " + body
                    )

                    # Personel alımı değilse geç
                    has_recruitment = contains_any(
                        searchable,
                        RECRUITMENT_TERMS
                    )

                    if not has_recruitment:
                        continue

                    # Eğitim şartı
                    has_high_school = contains_any(
                        searchable,
                        EDUCATION_TERMS
                    )

                    # KPSS şartı
                    has_kpss = contains_any(
                        searchable,
                        KPSS_TERMS
                    )

                    # Başvuru bitiş tarihi
                    deadline = extract_deadline(
                        body
                    )

                    # Eğitim uygunluğu
                    if has_high_school:
                        education_match = "possible"
                    else:
                        education_match = "not_confirmed"

                    items.append({
                        "source": source_name,
                        "source_url": target,
                        "title": page_title or title,
                        "recruitment_match": True,
                        "education_match": education_match,
                        "kpss_mentioned": has_kpss,
                        "application_deadline": deadline,
                        "application_status": determine_status(
                            deadline
                        ),
                        "last_checked": checked_at,
                        "verification": "manual_review_required",
                        "snippet": body[:500],
                    })

                except Exception as exc:

                    errors.append({
                        "source": source_name,
                        "url": target,
                        "error": str(exc)
                    })

        except Exception as exc:

            errors.append({
                "source": source_name,
                "error": str(exc)
            })

    # Tekrarlanan ilanları temizle
    unique_items = {
        item["source_url"]: item
        for item in items
    }

    final_items = list(
        unique_items.values()
    )

    return {
        "generated_at": checked_at,
        "status": (
            "ok" if not errors
            else "partial" if final_items
            else "error"
        ),
        "total_items": len(final_items),
        "items": final_items,
        "errors": errors,
    }


# --------------------------------------------------
# TEST
# --------------------------------------------------

if __name__ == "__main__":

    import json

    result = scan()

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
                        )
    
