"""Doc filler — realistic titles + body text for Google Docs files.

Used by gdrive's _generate_filler_files() for DOC mime type only.
Other mime types (sheets, PDFs, PNGs) keep simple placeholder content.

Ported from mock-gdoc's faker-based generator so that filler documents
are hard to distinguish from real needle content in search/cleanup tasks.
"""

from __future__ import annotations

import random

from faker import Faker

CATEGORIES = ["meeting_notes", "specs", "personal", "shared"]


def generate_doc_filler_title(fake: Faker, category: str, rng: random.Random) -> str:
    """Category-aware document title — unique per call via faker."""
    if category == "meeting_notes":
        templates = [
            f"Team Standup - {fake.date_this_month().strftime('%b %d')}",
            f"Sprint Retrospective - Sprint {rng.randint(10, 30)}",
            f"Design Review - {fake.catch_phrase()}",
            f"All Hands Notes - {fake.month_name()}",
            f"1:1 with {fake.first_name()} - {fake.date_this_month().strftime('%b %d')}",
        ]
    elif category == "specs":
        templates = [
            f"{fake.catch_phrase()} - Technical Spec",
            f"RFC: {fake.bs().title()}",
            f"{fake.company_suffix()} Integration Design",
            f"Architecture Decision Record - {fake.word().title()}",
        ]
    elif category == "personal":
        templates = [
            f"{fake.city()} Trip Notes",
            f"Book Notes: {fake.catch_phrase()}",
            f"Goals for {fake.month_name()}",
            f"Ideas - {fake.word().title()}",
        ]
    elif category == "shared":
        templates = [
            f"{fake.job()} Interview Questions",
            f"Team {fake.word().title()} Process",
            f"{fake.company_suffix()} Vendor Evaluation",
        ]
    else:
        templates = [f"Document - {fake.sentence(nb_words=4)}"]

    return rng.choice(templates)


def generate_doc_filler_content(fake: Faker, category: str, title: str, rng: random.Random) -> str:
    """Structured multi-paragraph body text matching the category."""
    paragraphs = [title, ""]

    if category == "meeting_notes":
        paragraphs.extend([
            f"Date: {fake.date_this_month().strftime('%B %d, %Y')}",
            f"Attendees: {', '.join(fake.name() for _ in range(rng.randint(3, 6)))}",
            "",
            "Discussion:",
            fake.paragraph(nb_sentences=4),
            "",
            "Action Items:",
        ])
        for _ in range(rng.randint(2, 5)):
            paragraphs.append(f"- [ ] {fake.name()}: {fake.sentence()}")
    elif category == "specs":
        paragraphs.extend([
            f"Author: {fake.name()}",
            f"Status: {rng.choice(['Draft', 'In Review', 'Approved'])}",
            "",
            "Overview:",
            fake.paragraph(nb_sentences=3),
            "",
            "Requirements:",
        ])
        for i in range(rng.randint(3, 6)):
            paragraphs.append(f"{i + 1}. {fake.sentence()}")
        paragraphs.extend([
            "",
            "Timeline:",
            fake.paragraph(nb_sentences=2),
        ])
    elif category == "personal":
        for _ in range(rng.randint(3, 6)):
            paragraphs.append(fake.paragraph(nb_sentences=rng.randint(2, 4)))
            paragraphs.append("")
    else:
        for _ in range(rng.randint(2, 4)):
            paragraphs.append(fake.paragraph(nb_sentences=rng.randint(2, 5)))
            paragraphs.append("")

    return "\n".join(paragraphs)
