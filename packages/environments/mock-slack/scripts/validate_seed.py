#!/usr/bin/env python3
"""Validate that the default seed data meets evaluator expectations.

Seeds a temporary database and asserts distribution invariants:
- expected users, channels, and messages are present
- thread structure is intact (reply_count > 0 on parents)
- DM channels exist and have messages
- files and pins are seeded
- reminders are seeded

Usage:
    python scripts/validate_seed.py
    python scripts/validate_seed.py --scenario long_context
"""

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG))

from mock_slack.models import reset_engine, init_db
from mock_slack.seed.generator import seed_database
from mock_slack.seed.content import PERSONAS, CHANNELS, BOT_USER, WORKSPACE_TEAM_ID


EXPECTED_HUMAN_USERS = len(PERSONAS)      # 10
EXPECTED_CHANNELS = len(CHANNELS)         # seeded channels (no DMs)
EXPECTED_MIN_MESSAGES = 30                # at least this many messages total
EXPECTED_MIN_THREADS = 1                  # at least one threaded message
EXPECTED_MIN_FILES = 1
EXPECTED_MIN_PINS = 1
EXPECTED_MIN_REMINDERS = 1
EXPECTED_MIN_DM_CHANNELS = 1


def validate(scenario: str = "default") -> bool:
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "validate.db")
        reset_engine()
        seed_database(scenario=scenario, seed=42, db_path=db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # ------------------------------------------------------------------
        # Workspace
        # ------------------------------------------------------------------
        ws = conn.execute("SELECT * FROM workspaces").fetchone()
        if ws is None:
            errors.append("FAIL: no workspace seeded")
        else:
            if ws["team_id"] != WORKSPACE_TEAM_ID:
                errors.append(f"FAIL: workspace team_id={ws['team_id']!r}, expected {WORKSPACE_TEAM_ID!r}")
            else:
                print(f"  OK  workspace '{ws['name']}' (team_id={ws['team_id']})")

        # ------------------------------------------------------------------
        # Users
        # ------------------------------------------------------------------
        users = conn.execute("SELECT * FROM slack_users").fetchall()
        human = [u for u in users if not u["is_bot"] and u["id"] != BOT_USER["id"]]
        bots = [u for u in users if u["is_bot"]]
        slackbot = next((u for u in users if u["id"] == BOT_USER["id"]), None)

        if len(human) != EXPECTED_HUMAN_USERS:
            errors.append(f"FAIL: {len(human)} human users, expected {EXPECTED_HUMAN_USERS}")
        else:
            print(f"  OK  {len(human)} human users")

        if slackbot is None:
            errors.append("FAIL: USLACKBOT not seeded")
        elif slackbot["is_bot"]:
            errors.append("FAIL: USLACKBOT has is_bot=True (should be False per real Slack API)")
        else:
            print(f"  OK  USLACKBOT present (is_bot=False)")

        if not bots:
            errors.append("FAIL: no bot user seeded (need at least one is_bot=True user)")
        else:
            print(f"  OK  {len(bots)} bot user(s)")

        # Check all persona emails are present
        persona_emails = {p["email"] for p in PERSONAS.values()}
        seeded_emails = {u["email"] for u in human if u["email"]}
        missing_emails = persona_emails - seeded_emails
        if missing_emails:
            errors.append(f"FAIL: missing persona emails: {missing_emails}")
        else:
            print(f"  OK  all {len(persona_emails)} persona emails present")

        # ------------------------------------------------------------------
        # Channels
        # ------------------------------------------------------------------
        channels = conn.execute("SELECT * FROM channels").fetchall()
        public = [c for c in channels if not c["is_private"] and not c["is_im"]]
        dms = [c for c in channels if c["is_im"]]

        if len(public) < EXPECTED_CHANNELS:
            errors.append(f"FAIL: {len(public)} public channels, expected >= {EXPECTED_CHANNELS}")
        else:
            print(f"  OK  {len(public)} public channels")

        # Check general exists
        general = next((c for c in channels if c["name"] == "general"), None)
        if general is None:
            errors.append("FAIL: 'general' channel not seeded")
        else:
            print(f"  OK  'general' channel present (id={general['id']})")

        if len(dms) < EXPECTED_MIN_DM_CHANNELS:
            errors.append(f"FAIL: {len(dms)} DM channels, expected >= {EXPECTED_MIN_DM_CHANNELS}")
        else:
            print(f"  OK  {len(dms)} DM channel(s)")

        # ------------------------------------------------------------------
        # Messages
        # ------------------------------------------------------------------
        messages = conn.execute("SELECT * FROM slack_messages").fetchall()
        top_level = [m for m in messages if not m["thread_ts"] or m["thread_ts"] == m["ts"]]
        replies = [m for m in messages if m["thread_ts"] and m["thread_ts"] != m["ts"]]
        threaded_parents = [m for m in messages if (m["reply_count"] or 0) > 0]

        if len(messages) < EXPECTED_MIN_MESSAGES:
            errors.append(f"FAIL: {len(messages)} messages, expected >= {EXPECTED_MIN_MESSAGES}")
        else:
            print(f"  OK  {len(messages)} messages total ({len(top_level)} top-level, {len(replies)} replies)")

        if len(threaded_parents) < EXPECTED_MIN_THREADS:
            errors.append(f"FAIL: {len(threaded_parents)} threaded parents, expected >= {EXPECTED_MIN_THREADS}")
        else:
            print(f"  OK  {len(threaded_parents)} threaded message(s) with replies")

        # Verify reply_count integrity: reply_count should equal actual replies
        mismatched = []
        for parent in threaded_parents:
            actual = conn.execute(
                "SELECT COUNT(*) FROM slack_messages WHERE thread_ts=? AND ts!=?",
                (parent["ts"], parent["ts"]),
            ).fetchone()[0]
            if actual != parent["reply_count"]:
                mismatched.append(
                    f"{parent['id']}: reply_count={parent['reply_count']} but {actual} actual replies"
                )
        if mismatched:
            errors.append(f"FAIL: reply_count mismatch on {len(mismatched)} message(s): {mismatched[:3]}")
        else:
            print(f"  OK  reply_count integrity verified on {len(threaded_parents)} parent(s)")

        # ------------------------------------------------------------------
        # Files
        # ------------------------------------------------------------------
        files = conn.execute("SELECT COUNT(*) FROM slack_files").fetchone()[0]
        if files < EXPECTED_MIN_FILES:
            errors.append(f"FAIL: {files} files, expected >= {EXPECTED_MIN_FILES}")
        else:
            print(f"  OK  {files} file(s)")

        # ------------------------------------------------------------------
        # Pins
        # ------------------------------------------------------------------
        pins = conn.execute("SELECT COUNT(*) FROM pins").fetchone()[0]
        if pins < EXPECTED_MIN_PINS:
            errors.append(f"FAIL: {pins} pins, expected >= {EXPECTED_MIN_PINS}")
        else:
            print(f"  OK  {pins} pin(s)")

        # ------------------------------------------------------------------
        # Reminders
        # ------------------------------------------------------------------
        reminders = conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]
        if reminders < EXPECTED_MIN_REMINDERS:
            errors.append(f"FAIL: {reminders} reminders, expected >= {EXPECTED_MIN_REMINDERS}")
        else:
            print(f"  OK  {reminders} reminder(s)")

        conn.close()
        reset_engine()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    if errors:
        print(f"\n{'='*60}")
        print(f"VALIDATION FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")
        return False
    else:
        print(f"\n{'='*60}")
        print("VALIDATION PASSED — seed data meets all expectations")
        return True


def main():
    parser = argparse.ArgumentParser(description="Validate mock-slack seed data")
    parser.add_argument("--scenario", default="default",
                        help="Scenario to seed (default: 'default')")
    args = parser.parse_args()

    print(f"Validating scenario: '{args.scenario}'")
    print("=" * 60)
    ok = validate(args.scenario)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
