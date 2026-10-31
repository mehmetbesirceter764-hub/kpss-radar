
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup


# ==================================================
# KAYNAKLAR
# ==================================================

SOURCES = [
    ("ÖSYM duyuruları", "https://www.osym.gov.tr/"),
    ("Kariyer Kapısı", "https://kariyerkapisi.gov.tr/isealim"),
]


# ==================================================
# İLAN KEŞİF KELİMELERİ
# ==================================================

DISCOVERY_TERMS = [
    "duyuru",
    "ilan",
    "alım",
    "alim",
    "başvuru",
    "basvuru",
    "personel",
    "memur",
    "işçi",
    "isci",
    "istihdam",
    "kadro",
    "sözleşmeli",
    "sozlesmeli",
    "uzman erbaş",
    "polis",
    "bekçi",
    "jandarma",
    "güvenlik",
    "zabıta",
    "itfaiye",
]


# ==================================================
# PERSONEL ALIMI KONTROLÜ
# ==================================================

RECRUITMENT_TERMS = [
    "personel alımı",
    "personel alim",
    "personel alımları",
    "memur alımı",
    "memur alim",
    "sözleşmeli personel",
    "sozlesmeli personel",
    "kamu işçisi",
    "kamu iscisi",
    "işçi alımı",
    "isci alimi",
    "sürekli işçi",
    "uzman erbaş",
    "sözleşmeli er",
    "polis alımı",
    "bekçi alımı",
    "jandarma alımı",
    "güvenlik görevlisi",
    "zabıta alımı",
    "itfaiye eri",
    "destek personeli",
    "personel istihdamı",
    "personel istihdami",
    "boş kadro",
    "bos kadro",
    "kadroya alım",
    "kadroya alim",
    "işe alım",
    "ise alim",
]


# ==================================================
# SINAV DUYURUSU KONTROLÜ
# ==================================================

EXAM_TERMS = [
    "sınav sonuçları açıklandı",
    "sinav sonuclari aciklandi",
    "cevap kağıtları",
    "cevap kagitlari",
    "soru kitapçığı",
    "soru kitapcigi",
    "sınav başvuruları",
    "sinav basvurulari",
    "sınav tarihi",
    "sinav tarihi",
    "sınava giriş belgesi",
    "sinava giris belgesi",
]


# ==================================================
# EĞİTİM VE KPSS ŞARTLARI
# ==================================================

EDUCATION_TERMS = [
    "ortaöğretim",
    "orta öğretim",
    "lise mezunu",
    "lise ve dengi",
    "lise veya dengi",
    "ortaöğretim mezunu",
    "en az lise",
    "lise düzeyinde",
]

KPSS_TERMS = [
    "kpss",
    "kpss p94",
    "p94 puan",
    "ortaöğretim kpss",
    "2024-kpss",
    "2026-kpss",
]


# ==================================================
# BAŞVURU TARİHLERİ
# ==================================================

DATE_PATTERNS = [
    r"son başvuru(?: tarihi)?[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    r"son başvuru tarihi[:\s]*(\d{1,2}\s+\w+\s+\d{4})",
    r"başvurular(?:ın)?\s+(?:son günü|bitiş tarihi)[:\s]*(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    r"başvurular\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+tarihinde sona",
    r"başvurular\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+tarihine kadar",
]


# ==================================================
# AYARLAR
# ==================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KPSS-Radar/1.0)"
}

TIMEOUT = 20

# Her kaynakta incelenecek bağlantı sınırı
MAX_DETAIL_PAGES = 60

# Aynı alan adı dışına çıkma
SAME_DOMAIN_ONLY = True


# ==================================================
# YARDIMCI FONKSİYONLAR
# ==================================================

def normalize(text):
    text = text.casefold()
    return " ".join(text.split())


def contains_any(text, terms):
    return any(term in text for term in terms)


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


def extract_text(soup):
    for tag in soup.find_all([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "noscript"
    ]):
        tag.decompose()

    return " ".join(
        soup.get_text(" ", strip=True).split()
    )


def extract_deadline(text):
    normalized = normalize(text)

    for pattern in DATE_PATTERNS:
        match = re.search(
            pattern,
            normalized
        )

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

        return (
            "open"
            if parsed >= today
            else "closed"
        )

    except ValueError:
        return "unknown"


def classify_education(text):
    if contains_any(text, EDUCATION_TERMS):
        return "possible"

    return "not_confirmed"


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

        if SAME_DOMAIN_ONLY:
            if parsed.netloc != source_domain:
                continue

        searchable = normalize(
            title + " " + target
        )

        if contains_any(
            searchable,
            DISCOVERY_TERMS
        ):
            candidates[target] = title

    return candidates


# ==================================================
# ANA TARAMA
# ==================================================

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
            source_page = get_page(
                session,
                source_url
            )

            candidates = discover_links(
                source_page,
                source_url
            )

            for target, title in list(
                candidates.items()
            )[:MAX_DETAIL_PAGES]:

                if target in seen_urls:
                    continue

                seen_urls.add(target)

                try:
                    detail = get_page(
                        session,
                        target
                    )

                    body = extract_text(detail)

                    page_title = (
                        detail.title.get_text(
                            " ",
                            strip=True
                        )
                        if detail.title
                        else title
                    )

                    searchable = normalize(
                        page_title + " " + body
                    )

                    # Personel alımı kontrolü
                    has_recruitment = contains_any(
                        searchable,
                        RECRUITMENT_TERMS
                    )

                    if not has_recruitment:
                        continue

                    # Sınav duyurusu kontrolü
                    is_exam_announcement = contains_any(
                        searchable,
                        EXAM_TERMS
                    )

                    if is_exam_announcement:
                        continue

                    # Eğitim ve KPSS kontrolü
                    education_match = classify_education(
                        searchable
                    )

                    has_kpss = contains_any(
                        searchable,
                        KPSS_TERMS
                    )

                    # Başvuru tarihi
                    deadline = extract_deadline(
                        body
                    )

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
                        "snippet": body[:700],
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


# ==================================================
# TEST VE RAPOR
# ==================================================

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
    
