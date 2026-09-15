"""
tests/test_duplicates.py: Unit tests for local duplicate detection and automatic priority escalation.
"""

import pytest
from services.duplicate_service import DuplicateService


def test_text_normalization_and_tokenization():
    raw = "Water leakage in Washroom, 3rd floor!! Please fix urgently."
    tokens = DuplicateService.get_tokens(raw)
    assert "leak" in tokens  # Stemmed from leakage
    assert "washroom" in tokens
    assert "floor" in tokens
    # Stopwords like "in", "please" are filtered
    assert "in" not in tokens
    assert "please" not in tokens


def test_similarity_exact_and_fuzzy():
    c1 = {
        "complaint_id": 101,
        "department_id": "dept-cse",
        "category_id": "cat-water",
        "location_id": "loc-main",
        "title": "Water leakage in 2nd floor washroom",
        "description": "Drinking water pipe is leaking continuously causing floor flooding."
    }
    c2 = {
        "complaint_id": 102,
        "department_id": "dept-cse",
        "category_id": "cat-water",
        "location_id": "loc-main",
        "title": "Severe water pipe leak in second floor washroom",
        "description": "Continuous water leakage from pipe is flooding the washroom floor."
    }
    score = DuplicateService.compute_similarity(c1, c2)
    assert score >= 0.70  # Should be recognized as duplicate

    # Mismatched department must yield 0.0
    c3 = dict(c2, department_id="dept-aids")
    assert DuplicateService.compute_similarity(c1, c3) == 0.0


def test_auto_priority_escalation_rules():
    # 1 complaint: student priority
    assert DuplicateService.calculate_auto_priority(1, "Low") == "Low"
    assert DuplicateService.calculate_auto_priority(1, "High") == "High"

    # 2-3 complaints: at least Medium
    assert DuplicateService.calculate_auto_priority(2, "Low") == "Medium"
    assert DuplicateService.calculate_auto_priority(3, "Low") == "Medium"
    assert DuplicateService.calculate_auto_priority(3, "High") == "High"

    # 4-5 complaints: at least High
    assert DuplicateService.calculate_auto_priority(4, "Low") == "High"
    assert DuplicateService.calculate_auto_priority(5, "Medium") == "High"
    assert DuplicateService.calculate_auto_priority(5, "Urgent") == "Urgent"

    # 6+ complaints: Urgent
    assert DuplicateService.calculate_auto_priority(6, "Low") == "Urgent"
    assert DuplicateService.calculate_auto_priority(10, "Medium") == "Urgent"


def test_manual_priority_minimum_enforcement():
    # If auto minimum is High, manual Low or Medium is rejected
    auto_min = "High"
    assert not DuplicateService.is_manual_priority_allowed("Low", auto_min)
    assert not DuplicateService.is_manual_priority_allowed("Medium", auto_min)
    assert DuplicateService.is_manual_priority_allowed("High", auto_min)
    assert DuplicateService.is_manual_priority_allowed("Urgent", auto_min)
