
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


SOURCES = [
    ("ÖSYM duyuruları", "https://www.osym.gov.tr/"),
    ("Kariyer Kapısı", "https://kariyerkapisi.gov.tr/isealim"),
]

DISCOVERY_TERMS = [
    "duyuru", "ilan", "alım", "alim", "başvuru", "basvuru",
    "personel", "memur", "işçi", "isci", "istihdam", "kadro",
    "sözleşmeli", "sozlesmeli", "uzman erbaş", "polis",
    "bekçi", "jandarma", "güvenlik", "zabıta", "itfaiye",
]

RECRUITMENT_TERMS = [
    "personel alımı", "personel alim", "memur alımı", "memur alim",
    "sözleşmeli personel", "sozlesmeli personel",
    "kamu işçisi", "kamu iscisi", "işçi alımı", "isci alimi",
    "sürekli işçi", "uzman erbaş", "sözleşmeli er",
    "polis alımı", "bekçi alımı", "jandarma alımı",
    "güvenlik görevlisi", "zabıta alımı", "itfaiye eri",
    "destek personeli", "personel istihdamı", "personel istihdami",
    "boş kadro", "bos kadro", "kadroya alım", "kadroya alim",
    "işe alım", "ise alim",
]

EDUCATION_TERMS = [
    "ortaöğretim", "orta öğretim", "lise mezunu",
    "lise ve dengi", "lise veya dengi",
    "ortaöğretim mezunu", "en az lise", "lise düzeyinde",
]

KPSS_TERMS = [
    "kpss", "kpss p94", "p94 puan",
    "ortaöğretim kpss", "2024-kpss", "2026-kpss",
]

EXAM_ONLY_TERMS = [
    "sınav sonuçları açıklandı",
    "sinav sonuclari aciklandi",
    "cevap kağıtları yayımlandı",
    "cevap kagitlari yayimlandi",
    "soru kitapçığı yayımlandı",
    "soru kitapcigi yayimlandi",
    "sınava giriş belgesi yayımlandı",
    "sinava giris belgesi yayimlandi",
]

DATE_PATTERNS = [
    r"son başvuru(?: tarihi)?[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    r"başvurular(?:ın)?\s+(?:son günü|bitiş tarihi)[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    r"başvurular\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+tarihinde sona",
    r"başvurular\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+tarihine kadar",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KPSS-Radar/1.0)"
}

TIMEOUT = 20
MAX_DETAIL_PAGES = 60


def normalize(text):
    return " ".join(text.casefold().split())


def contains_any(text, terms):
    return any(term in text for term in terms)


def get_page(session, url):
    response = session.get(
        url,
        timeout=TIMEOUT,
        headers=HEADERS
    )
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


def extract_text(soup):
    for tag in soup.find_all([
        "script", "style", "nav", "footer",
        "header", "noscript"
    ]):
        tag.decompose()

    return " ".join(soup.get_text(" ", strip=True).split())


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

        return "open" if parsed >= today else "closed"

    except ValueError:
        return "unknown"


def discover_links(soup, source_url):
    candidates = {}
    source_domain = urlparse(source_url).netloc

    for link in soup.find_all("a", href=True):
        title = " ".join(
            link.get_text(" ", strip=True).split()
        )

        target = urldefrag(
            urljoin(source_url, link["href"])
        ).url

        parsed = urlparse(target)

        if not title:
            continue

        if parsed.scheme not in ("http", "https"):
            continue

        if parsed.netloc != source_domain:
            continue

        searchable = normalize(title + " " + target)

        if contains_any(searchable, DISCOVERY_TERMS):
            candidates[target] = title

    return candidates


def scan():
    items = []
    errors = []
    seen_urls = set()

    counters = {
        "sources_checked": 0,
        "links_discovered": 0,
        "pages_checked": 0,
        "rejected_pages": 0,
        "rejection_reasons": {},
    }

    source_stats = []

    rejection_counts = Counter()

    session = requests.Session()

    checked_at = datetime.now(timezone.utc).isoformat()

    for source_name, source_url in SOURCES:
        stats = {
            "source": source_name,
            "source_url": source_url,
            "source_accessed": False,
            "links_discovered": 0,
            "pages_checked": 0,
            "items_found": 0,
            "error": None,
        }

        counters["sources_checked"] += 1

        try:
            source_page = get_page(session, source_url)
            stats["source_accessed"] = True

            candidates = discover_links(
                source_page,
                source_url
            )

            stats["links_discovered"] = len(candidates)
            counters["links_discovered"] += len(candidates)

            for target, title in list(
                candidates.items()
            )[:MAX_DETAIL_PAGES]:

                if target in seen_urls:
                    continue

                seen_urls.add(target)

                try:
                    detail = get_page(session, target)
                    body = extract_text(detail)

                    page_title = (
                        detail.title.get_text(" ", strip=True)
                        if detail.title
                        else title
                    )

                    searchable = normalize(
                        page_title + " " + body
                    )

                    counters["pages_checked"] += 1
                    stats["pages_checked"] += 1

                    # Personel alımı ifadesi bulunamadı
                    if not contains_any(
                        searchable,
                        RECRUITMENT_TERMS
                    ):
                        rejection_counts[
                            "recruitment_term_not_found"
                        ] += 1
                        counters["rejected_pages"] += 1
                        continue

                    # Sadece sınav sonucu/evrak duyurusu olan sayfalar
                    if contains_any(
                        searchable,
                        EXAM_ONLY_TERMS
                    ):
                        rejection_counts[
                            "exam_announcement"
                        ] += 1
                        counters["rejected_pages"] += 1
                        continue

                    has_education = contains_any(
                        searchable,
                        EDUCATION_TERMS
                    )

                    has_kpss = contains_any(
                        searchable,
                        KPSS_TERMS
                    )

                    deadline = extract_deadline(body)

                    items.append({
                        "source": source_name,
                        "source_url": target,
                        "title": page_title or title,
                        "recruitment_match": True,
                        "education_match": (
                            "possible"
                            if has_education
                            else "not_confirmed"
                        ),
                        "kpss_mentioned": has_kpss,
                        "application_deadline": deadline,
                        "application_status": determine_status(
                            deadline
                        ),
                        "last_checked": checked_at,
                        "verification": "manual_review_required",
                        "snippet": body[:700],
                    })

                    stats["items_found"] += 1

                except Exception as exc:
                    errors.append({
                        "source": source_name,
                        "url": target,
                        "error": str(exc),
                    })

        except Exception as exc:
            stats["error"] = str(exc)

            errors.append({
                "source": source_name,
                "url": source_url,
                "error": str(exc),
            })

        source_stats.append(stats)

    # Aynı URL'den gelen tekrarları temizle
    unique_items = {
        item["source_url"]: item
        for item in items
    }

    final_items = list(unique_items.values())

    counters["rejection_reasons"] = dict(
        rejection_counts
    )

    # Kaynak erişilemediyse tarama tam başarılı sayılmaz
    accessible_sources = sum(
        1 for source in source_stats
        if source["source_accessed"]
    )

    if len(errors) == 0:
        status = "ok"
    elif accessible_sources > 0:
        status = "partial"
    else:
        status = "error"

    return {
        "generated_at": checked_at,
        "status": status,
        "summary": {
            "total_items": len(final_items),
            "sources_checked": counters["sources_checked"],
            "links_discovered": counters["links_discovered"],
            "pages_checked": counters["pages_checked"],
            "rejected_pages": counters["rejected_pages"],
        },
        "counters": counters,
        "source_stats": source_stats,
        "total_items": len(final_items),
        "items": final_items,
        "errors": errors,
    }


if __name__ == "__main__":
    import json

    print(
        json.dumps(
            scan(),
            ensure_ascii=False,
            indent=2
        )
)
            
