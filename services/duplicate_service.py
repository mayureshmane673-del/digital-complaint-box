"""
services/duplicate_service.py: Local modular NLP and similarity algorithm.
Detects similar/duplicate complaints and manages automatic priority escalation without paid external AI APIs.
"""

import re
from typing import List, Dict, Any, Tuple, Optional

PRIORITY_LEVELS = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Urgent": 4
}

COMMON_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "for", "is", "of", "while", "during",
    "to", "from", "in", "out", "on", "off", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "can", "will", "don",
    "should", "now", "it", "its", "at", "by", "with", "we", "our", "my", "me",
    "sir", "madam", "please", "kindly", "problem", "issue", "complaint"
}


class DuplicateService:
    @staticmethod
    def normalize_text(text: str) -> str:
        """Lowercases, removes punctuation, and normalizes whitespace."""
        if not text:
            return ""
        lowered = text.lower()
        cleaned = re.sub(r"[^\w\s]", " ", lowered)
        return " ".join(cleaned.split())

    @classmethod
    def get_tokens(cls, text: str) -> List[str]:
        """Tokenizes text and filters out common stopwords."""
        clean = cls.normalize_text(text)
        return [w for w in clean.split() if w not in COMMON_STOPWORDS and len(w) > 1]

    @classmethod
    def jaccard_similarity(cls, tokens1: List[str], tokens2: List[str]) -> float:
        """Calculates token Jaccard similarity coefficient."""
        s1 = set(tokens1)
        s2 = set(tokens2)
        if not s1 or not s2:
            return 0.0
        intersection = len(s1.intersection(s2))
        union = len(s1.union(s2))
        return float(intersection) / float(union) if union > 0 else 0.0

    @classmethod
    def ngram_similarity(cls, text1: str, text2: str, n: int = 3) -> float:
        """Calculates character n-gram similarity for catching typos and variants."""
        c1 = cls.normalize_text(text1)
        c2 = cls.normalize_text(text2)
        if not c1 or not c2:
            return 0.0
        ng1 = set(c1[i:i + n] for i in range(len(c1) - n + 1))
        ng2 = set(c2[i:i + n] for i in range(len(c2) - n + 1))
        if not ng1 or not ng2:
            return 0.0
        inter = len(ng1.intersection(ng2))
        union = len(ng1.union(ng2))
        return float(inter) / float(union) if union > 0 else 0.0

    @staticmethod
    def stem_token(word: str) -> str:
        """Basic suffix normalization for common English variations."""
        w = word.lower()
        # Common word equivalents
        if w in ("2nd", "second"):
            return "2"
        if w in ("1st", "first"):
            return "1"
        if w in ("3rd", "third"):
            return "3"
        for suffix in ("ing", "ed", "age", "es", "s"):
            if w.endswith(suffix) and len(w) > len(suffix) + 2:
                return w[:-len(suffix)]
        return w

    @classmethod
    def get_tokens(cls, text: str) -> List[str]:
        """Tokenizes text, strips stopwords, and applies light stemming."""
        clean = cls.normalize_text(text)
        tokens = [w for w in clean.split() if w not in COMMON_STOPWORDS and len(w) > 1]
        return [cls.stem_token(t) for t in tokens]

    @classmethod
    def compute_similarity(cls, c1: Dict[str, Any], c2: Dict[str, Any]) -> float:
        """
        Mandatory 3-Dimension Classification & Scope Duplicate Detection:
        1. Same Category (compulsory: mismatch -> 0.0)
        2. Same Subcategory (compulsory if specified: mismatch -> 0.0)
        3. Same Priority (compulsory if specified: mismatch -> 0.0)
        4. Scope matching (Hostel vs Academic vs Library: mismatch -> 0.0)
        
        Only when the above match:
        - Location match: 0.30 weight
        - Title & Description token overlap + n-gram similarity: 0.70 weight
        Threshold for duplicate is 0.65.
        """
        # Scope: Hostel check
        h1 = bool(c1.get("is_hostel"))
        h2 = bool(c2.get("is_hostel"))
        if h1 != h2:
            return 0.0

        # Scope: Academic Department check (for non-hostel)
        d1 = str(c1.get("department_id") or "")
        d2 = str(c2.get("department_id") or "")
        if not h1 and d1 and d2 and d1 != d2:
            return 0.0

        # 1. Category match (compulsory)
        cat1 = str(c1.get("category_id") or c1.get("category_name") or c1.get("category_custom") or "").strip().lower()
        cat2 = str(c2.get("category_id") or c2.get("category_name") or c2.get("category_custom") or "").strip().lower()
        if cat1 and cat2 and cat1 != cat2:
            return 0.0
        if not cat1 or not cat2:
            # If neither has category info, cannot verify category
            pass

        # 2. Subcategory match (compulsory if provided in either)
        sub1 = str(c1.get("subcategory_id") or c1.get("subcategory_name") or c1.get("subcategory_custom") or "").strip().lower()
        sub2 = str(c2.get("subcategory_id") or c2.get("subcategory_name") or c2.get("subcategory_custom") or "").strip().lower()
        if sub1 and sub2 and sub1 != sub2:
            return 0.0

        # 3. Priority match (compulsory if provided in both)
        prio1 = str(c1.get("priority") or "").strip().lower()
        prio2 = str(c2.get("priority") or "").strip().lower()
        if prio1 and prio2 and prio1 != prio2:
            return 0.0

        # Structured base score (exact Category match guaranteed at this point)
        category_base = 0.25
        loc1 = str(c1.get("location_id") or c1.get("location_custom") or c1.get("location_name") or "").strip().lower()
        loc2 = str(c2.get("location_id") or c2.get("location_custom") or c2.get("location_name") or "").strip().lower()
        location_score = 0.25 if (loc1 and loc2 and loc1 == loc2) else (0.10 if (not loc1 or not loc2) else 0.0)

        # Title similarity (40% of text score)
        t_tokens1 = cls.get_tokens(c1.get("title", ""))
        t_tokens2 = cls.get_tokens(c2.get("title", ""))
        title_jac = cls.jaccard_similarity(t_tokens1, t_tokens2)
        title_ng = cls.ngram_similarity(c1.get("title", ""), c2.get("title", ""))
        title_score = 0.5 * title_jac + 0.5 * title_ng

        # Description similarity (60% of text score)
        d_tokens1 = cls.get_tokens(c1.get("description", ""))
        d_tokens2 = cls.get_tokens(c2.get("description", ""))
        desc_jac = cls.jaccard_similarity(d_tokens1, d_tokens2)
        desc_ng = cls.ngram_similarity(c1.get("description", ""), c2.get("description", ""))
        desc_score = 0.5 * desc_jac + 0.5 * desc_ng

        text_score = 0.40 * title_score + 0.60 * desc_score

        # Composite score
        composite = category_base + location_score + (0.50 * text_score)

        return min(1.0, round(composite, 3))

    @classmethod
    def find_duplicates(
        cls,
        target_complaint: Dict[str, Any],
        candidate_complaints: List[Dict[str, Any]],
        threshold: float = 0.65
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Finds all complaints with similarity score above the threshold.
        Returns list of (candidate, score) sorted descending by score.
        """
        duplicates = []
        target_id = target_complaint.get("complaint_id")

        for cand in candidate_complaints:
            # Skip self or deleted
            if cand.get("complaint_id") == target_id or cand.get("is_deleted"):
                continue
            score = cls.compute_similarity(target_complaint, cand)
            if score >= threshold:
                duplicates.append((cand, score))

        duplicates.sort(key=lambda x: x[1], reverse=True)
        return duplicates

    @staticmethod
    def calculate_auto_priority(duplicate_count: int, initial_priority: str = "Low") -> str:
        """
        Calculates automatic minimum priority based on duplicate count:
        - 1 complaint: student-selected priority
        - 2-3 similar: at least Medium
        - 4-5 similar: at least High
        - 6+ similar: Urgent
        """
        base_level = PRIORITY_LEVELS.get(initial_priority, 1)

        if duplicate_count >= 6:
            min_level = 4  # Urgent
        elif duplicate_count >= 4:
            min_level = 3  # High
        elif duplicate_count >= 2:
            min_level = 2  # Medium
        else:
            min_level = 1  # Low

        final_level = max(base_level, min_level)
        for name, lvl in PRIORITY_LEVELS.items():
            if lvl == final_level:
                return name
        return "Urgent"

    @staticmethod
    def is_manual_priority_allowed(manual_priority: str, auto_minimum_priority: str) -> bool:
        """
        Validates whether a manually selected priority satisfies the automatic minimum.
        Manual priority cannot be lower than the automatic minimum!
        """
        manual_lvl = PRIORITY_LEVELS.get(manual_priority, 1)
        min_lvl = PRIORITY_LEVELS.get(auto_minimum_priority, 1)
        return manual_lvl >= min_lvl
