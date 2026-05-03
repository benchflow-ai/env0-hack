#!/usr/bin/env python3
"""Validate seed data meets evaluator expectations.

Runs classification on seeded documents and asserts distribution invariants.
Use this after modifying seed content or generator logic to catch regressions.

Usage:
    python scripts/validate_seed.py                     # validate default scenario
    python scripts/validate_seed.py --scenario long_context
    python scripts/validate_seed.py --scenario task:gdoc-search-by-title
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


def validate(scenario: str = "default", seed: int = 42) -> bool:
    """Validate seed data for a given scenario. Returns True if all checks pass."""
    from mock_gdoc.models import reset_engine, get_session_factory, Document, User
    from mock_gdoc.seed.generator import seed_database
    from mock_gdoc.seed.body_builder import extract_plain_text

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "validate.db")
        reset_engine()
        stats = seed_database(scenario=scenario, seed=seed, db_path=db_path)

        SessionLocal = get_session_factory()
        db = SessionLocal()

        try:
            users = db.query(User).all()
            documents = db.query(Document).all()

            print(f"Scenario: {scenario}")
            print(f"Users: {len(users)}")
            print(f"Documents: {len(documents)}")
            print()

            errors = []

            # Basic invariants
            if len(users) == 0:
                errors.append("No users created")
            if len(documents) == 0:
                errors.append("No documents created")

            # Scenario-specific checks
            if scenario == "default":
                if len(documents) < 50:
                    errors.append(f"Default scenario should have >= 50 docs, got {len(documents)}")
                if len(documents) > 200:
                    errors.append(f"Default scenario should have <= 200 docs, got {len(documents)}")

            elif scenario == "long_context":
                if len(documents) < 2800:
                    errors.append(f"Long context should have >= 2800 docs, got {len(documents)}")

            elif scenario.startswith("task:"):
                task_name = scenario.removeprefix("task:")
                if len(documents) < 10:
                    errors.append(f"Task scenario should have >= 10 docs, got {len(documents)}")

                # Check needle documents exist
                _validate_task_needles(db, task_name, documents, errors)

            # Check all documents have valid body structure
            docs_without_body = 0
            docs_with_empty_body = 0
            for doc in documents:
                body = doc.body
                if not body:
                    docs_without_body += 1
                    continue
                content = body.get("content", [])
                if not content:
                    docs_with_empty_body += 1
                    continue

                # Verify body has at least one textRun
                has_text = False
                for el in content:
                    p = el.get("paragraph")
                    if p:
                        for pe in p.get("elements", []):
                            if pe.get("textRun", {}).get("content"):
                                has_text = True
                                break
                    if has_text:
                        break

            print(f"Documents with body: {len(documents) - docs_without_body}")
            print(f"Documents with empty body: {docs_with_empty_body}")
            print(f"Documents without body: {docs_without_body}")

            if docs_without_body > 0:
                errors.append(f"{docs_without_body} documents have no body")

            # Check titles are unique-ish (allow some duplicates from filler)
            titles = [d.title for d in documents]
            unique_titles = set(titles)
            dup_ratio = 1 - len(unique_titles) / len(titles) if titles else 0
            print(f"Title uniqueness: {len(unique_titles)}/{len(titles)} ({1-dup_ratio:.0%})")
            if dup_ratio > 0.3:
                errors.append(f"Too many duplicate titles: {dup_ratio:.0%} duplicates")

            # Report
            print()
            if errors:
                print("VALIDATION FAILED:")
                for e in errors:
                    print(f"  ✗ {e}")
                return False
            else:
                print("VALIDATION PASSED")
                return True

        finally:
            db.close()
            reset_engine()


def _validate_task_needles(db, task_name: str, documents, errors: list):
    """Check that needle documents from the task are present in the seeded DB."""
    import importlib.util
    import os

    tasks_dir = os.environ.get("TASKS_DIR")
    if tasks_dir:
        needles_path = Path(tasks_dir) / task_name / "data" / "needles.py"
    else:
        # Walk up from scripts/ to repo root: scripts/ → mock-gdoc/ → environments/ → packages/ → repo
        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        needles_path = repo_root / "tasks" / task_name / "data" / "needles.py"

    if not needles_path.exists():
        errors.append(f"needles.py not found at {needles_path}")
        return

    spec = importlib.util.spec_from_file_location("needles", needles_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    needle_docs = getattr(module, "NEEDLE_DOCUMENTS", [])
    if not needle_docs:
        errors.append("NEEDLE_DOCUMENTS is empty in needles.py")
        return

    doc_titles = {d.title for d in documents}
    doc_ids = {d.id for d in documents}

    print(f"Needle documents expected: {len(needle_docs)}")
    for nd in needle_docs:
        title = nd.get("title", "")
        doc_id = nd.get("id")

        found = False
        if doc_id and doc_id in doc_ids:
            found = True
        elif title in doc_titles:
            found = True

        if found:
            print(f"  ✓ {title}")
        else:
            print(f"  ✗ {title} (NOT FOUND)")
            errors.append(f"Needle document not found: {title}")


def main():
    parser = argparse.ArgumentParser(description="Validate mock-gdoc seed data")
    parser.add_argument("--scenario", default="default", help="Seed scenario to validate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    success = validate(scenario=args.scenario, seed=args.seed)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
