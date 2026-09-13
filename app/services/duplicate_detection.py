import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Optional, Sequence, Union
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.Scholarship import Scholarship

# Common Arabic diacritics / tashkeel
ARABIC_DIACRITICS_REGEX = re.compile(r"[\u064B-\u0652\u0670\u0640]")  # includes tatweel

def normalize_arabic_letters(text: str) -> str:
    """Normalize Arabic letter variations and remove tashkeel and tatweel."""
    # Strip diacritics and tatweel
    text = ARABIC_DIACRITICS_REGEX.sub("", text)
    # Normalize Alef forms
    text = re.sub(r"[إأآٱ]", "ا", text)
    # Normalize Taa Marbouta to Haa
    text = re.sub(r"ة\b", "ه", text)
    # Normalize Alif Maqsoora to Yaa
    text = re.sub(r"ى\b", "ي", text)
    return text


def normalize_text(text: Optional[str]) -> str:
    """Clean and normalize Arabic and English text for comparison."""
    if not text:
        return ""
    # Lowercase English letters
    cleaned = text.strip().lower()
    # Normalize Arabic letters
    cleaned = normalize_arabic_letters(cleaned)
    # Replace punctuation and special characters with spaces
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Collapse multiple whitespaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# Arabic and English stop words commonly appearing in scholarship titles
RAW_STOP_WORDS = {
    # Arabic
    "منحة",
    "منح",
    "دراسية",
    "دراسة",
    "برنامج",
    "فرصة",
    "في",
    "من",
    "على",
    "إلى",
    "الى",
    "عن",
    "مع",
    "لـ",
    "للطلاب",
    "جامعة",
    "جامعات",
    "كاملة",
    "ممولة",
    "بالكامل",
    "جزئية",
    "الدولية",
    "العالمية",
    # English
    "scholarship",
    "scholarships",
    "fellowship",
    "grant",
    "program",
    "programme",
    "study",
    "for",
    "in",
    "at",
    "the",
    "and",
    "of",
    "to",
    "university",
    "college",
    "international",
    "fully",
    "funded",
}

STOP_WORDS = {normalize_text(w) for w in RAW_STOP_WORDS if normalize_text(w)}



def tokenize(text: Optional[str], remove_stop_words: bool = True) -> list[str]:
    """Tokenize normalized text and optionally remove stop words."""
    cleaned = normalize_text(text)
    if not cleaned:
        return []
    tokens = cleaned.split()
    if remove_stop_words:
        filtered = [t for t in tokens if t not in STOP_WORDS and len(t) > 1]
        return filtered if filtered else tokens
    return tokens


def calculate_jaccard_similarity(tokens1: Sequence[str], tokens2: Sequence[str]) -> float:
    """Calculate Jaccard similarity between two token sets."""
    set1, set2 = set(tokens1), set(tokens2)
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def calculate_text_similarity(text1: Optional[str], text2: Optional[str]) -> float:
    """
    Compute a combined similarity score between two text strings.
    Combines token Jaccard similarity (word order agnostic) with
    SequenceMatcher (handles minor character typos and variations).
    """
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    if not norm1 and not norm2:
        return 1.0
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0

    tokens1 = tokenize(text1, remove_stop_words=True)
    tokens2 = tokenize(text2, remove_stop_words=True)
    jaccard_score = calculate_jaccard_similarity(tokens1, tokens2)

    seq_raw = SequenceMatcher(None, norm1, norm2).ratio()
    sorted_str1 = " ".join(sorted(tokens1))
    sorted_str2 = " ".join(sorted(tokens2))
    seq_sorted = (
        SequenceMatcher(None, sorted_str1, sorted_str2).ratio()
        if sorted_str1 and sorted_str2
        else seq_raw
    )
    sequence_score = max(seq_raw, seq_sorted)

    # Blend Jaccard (60%) and SequenceMatcher (40%)
    return (0.60 * jaccard_score) + (0.40 * sequence_score)


def normalize_url(url: Optional[str]) -> Optional[str]:
    """
    Clean and canonicalize URLs for accurate comparison.
    Strips tracking query parameters (utm_*, ref, etc.), trailing slashes,
    and standardizes schemes to lowercase.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/")

        # Filter out common marketing/tracking query parameters
        tracking_params = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "ref",
            "fbclid",
            "gclid",
            "_ga",
        }
        query_dict = parse_qs(parsed.query, keep_blank_values=False)
        cleaned_query = {k: v for k, v in query_dict.items() if k.lower() not in tracking_params}
        sorted_query = urlencode(cleaned_query, doseq=True)

        return urlunparse(
            (
                parsed.scheme.lower(),
                netloc,
                path,
                "",  # params
                sorted_query,
                "",  # fragment
            )
        )
    except Exception:
        return url.strip().rstrip("/").lower()


def compare_scholarships(
    target: Union[Scholarship, dict[str, Any]],
    candidate: Scholarship,
) -> tuple[float, list[str]]:
    """
    Evaluate similarity between a target scholarship and a database candidate.
    Returns:
        similarity_score: float between 0.0 and 1.0
        reasons: list of explanations in Arabic detailing why it matched
    """
    # Helper to extract fields from either an ORM instance or a dict
    def get_val(obj: Any, field_name: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(field_name)
        return getattr(obj, field_name, None)

    target_title = get_val(target, "title") or ""
    target_org = get_val(target, "organization_name") or ""
    target_country = get_val(target, "country") or ""
    target_apply_link = get_val(target, "apply_link")
    target_deadline = get_val(target, "deadline")

    cand_title = candidate.title or ""
    cand_org = candidate.organization_name or ""
    cand_country = candidate.country or ""
    cand_apply_link = candidate.apply_link
    cand_deadline = candidate.deadline

    reasons: list[str] = []

    # 1. URL Signal: apply_link comparison
    norm_target_url = normalize_url(target_apply_link)
    norm_cand_url = normalize_url(cand_apply_link)
    url_match = (
        bool(norm_target_url and norm_cand_url and norm_target_url == norm_cand_url)
    )

    if url_match:
        reasons.append("تطابق تام في رابط التقديم المباشر")

    # 2. Text Signal: Title similarity
    title_sim = calculate_text_similarity(target_title, cand_title)
    if title_sim >= 0.80:
        reasons.append(f"تشابه كبير جداً في العنوان ({int(title_sim * 100)}%)")
    elif title_sim >= 0.60:
        reasons.append(f"تشابه ملحوظ في العنوان ({int(title_sim * 100)}%)")

    # 3. Text Signal: Organization similarity
    org_sim = calculate_text_similarity(target_org, cand_org)
    if target_org and cand_org and org_sim >= 0.70:
        reasons.append(f"تطابق في اسم المؤسسة أو الجامعة المانحة ({target_org})")

    # 4. Context Signal: Country matching & conflict check
    norm_target_country = normalize_text(target_country)
    norm_cand_country = normalize_text(cand_country)
    countries_conflict = False

    if norm_target_country and norm_cand_country:
        if norm_target_country == norm_cand_country:
            reasons.append(f"تطابق في دولة المنحة ({target_country})")
        else:
            # Different explicit countries
            countries_conflict = True

    # 5. Deadline proximity signal
    deadline_matched = False
    if target_deadline and cand_deadline:
        if isinstance(target_deadline, str):
            try:
                target_deadline = date.fromisoformat(target_deadline)
            except ValueError:
                target_deadline = None

        if isinstance(cand_deadline, str):
            try:
                cand_deadline = date.fromisoformat(cand_deadline)
            except ValueError:
                cand_deadline = None

        if target_deadline and cand_deadline and target_deadline == cand_deadline:
            deadline_matched = True
            reasons.append(f"تطابق الموعد النهائي للتقديم ({target_deadline})")

    # Composite Score Calculation
    if url_match and not countries_conflict:
        # Identical apply link without conflicting country is an almost certain duplicate
        final_score = max(0.92, min(1.0, (title_sim * 0.25) + 0.75))
    elif url_match and countries_conflict:
        # Conflict in country despite same URL: possible multi-campus or portal
        final_score = 0.65
    else:
        # Standard weighted model
        # Base: Title is primary (70%), Organization (15%), Country match (15%)
        base_score = title_sim * 0.70
        if target_org and cand_org:
            base_score += org_sim * 0.15
        else:
            # Reallocate weight to title if org is absent
            base_score += title_sim * 0.15

        if norm_target_country and norm_cand_country and not countries_conflict:
            base_score += 0.15
        elif not norm_target_country or not norm_cand_country:
            # No explicit conflict, slight neutral weight
            base_score += 0.05

        if deadline_matched:
            base_score += 0.05

        if countries_conflict:
            # Heavy penalty when countries explicitly differ (e.g. Turkey vs UK)
            base_score *= 0.40

        final_score = min(1.0, max(0.0, base_score))

    return round(final_score, 2), reasons


def find_duplicate_candidates(
    db: Session,
    target: Union[Scholarship, dict[str, Any]],
    threshold: float = 0.75,
    limit: int = 5,
    exclude_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Search database for scholarships matching the target scholarship above the given threshold.
    Filters candidate pool intelligently to maintain fast query response times.
    """
    def get_val(obj: Any, field_name: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(field_name)
        return getattr(obj, field_name, None)

    target_country = get_val(target, "country")
    target_apply_link = get_val(target, "apply_link")
    norm_url = normalize_url(target_apply_link)

    query = db.query(Scholarship)
    if exclude_id is not None:
        query = query.filter(Scholarship.id != exclude_id)

    # Filtering strategy:
    # 1. Matches on apply_link OR
    # 2. Same country (or country is null)
    conditions = []
    if norm_url:
        conditions.append(Scholarship.apply_link.isnot(None))
    if target_country:
        conditions.append(
            or_(
                Scholarship.country.ilike(f"%{target_country.strip()}%"),
                Scholarship.country.is_(None),
            )
        )

    if conditions:
        candidates_query = query.filter(or_(*conditions))
    else:
        candidates_query = query

    # Limit maximum database rows evaluated to keep latency bounded
    raw_candidates = candidates_query.limit(200).all()

    scored_candidates = []
    for candidate in raw_candidates:
        score, reasons = compare_scholarships(target, candidate)
        if score >= threshold:
            scored_candidates.append(
                {
                    "id": candidate.id,
                    "title": candidate.title,
                    "source": candidate.source,
                    "status": candidate.status,
                    "country": candidate.country,
                    "organization_name": candidate.organization_name,
                    "similarity_score": score,
                    "reasons": reasons,
                }
            )

    # Sort descending by similarity score
    scored_candidates.sort(key=lambda c: c["similarity_score"], reverse=True)
    return scored_candidates[:limit]
