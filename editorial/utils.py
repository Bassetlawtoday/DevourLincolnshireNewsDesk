"""Shared helper functions for the editorial package."""

import re


def clean_text(value):
    return " ".join(str(value or "").split())


def contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def normalise_category(value):
    category = clean_text(value)
    return category if category else "Uncategorised"


def numbers_in_text(text):
    return [int(v) for v in re.findall(r"\b\d{1,4}\b", text)]