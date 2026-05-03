"""Tests for received_at support in task_seed._insert_needle_emails.

Verifies that needles with an absolute `received_at` ISO date string are
seeded with that exact timestamp, while needles using `days_ago` continue
to work as before.
"""

import random
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mock_gmail.models import Base, User, Message
from mock_gmail.seed.task_seed import _insert_needle_emails


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def user(db):
    u = User(
        id="user1",
        email_address="test@example.com",
        display_name="Test User",
    )
    db.add(u)
    db.commit()
    return u


class TestReceivedAt:
    def test_received_at_sets_exact_date(self, db, user):
        needle = {
            "sender_name": "Sender",
            "sender_email": "s@example.com",
            "subject": "Fixed date email",
            "body_plain": "body",
            "labels": ["INBOX"],
            "received_at": "2025-03-15T10:00:00",
        }
        _insert_needle_emails(db, user, [needle], datetime.utcnow(), random)
        db.commit()

        msg = db.query(Message).filter_by(subject="Fixed date email").one()
        assert msg.internal_date == datetime(2025, 3, 15, 10, 0, 0)

    def test_received_at_takes_precedence_over_days_ago(self, db, user):
        needle = {
            "sender_name": "Sender",
            "sender_email": "s@example.com",
            "subject": "Precedence test",
            "body_plain": "body",
            "labels": ["INBOX"],
            "received_at": "2025-03-10T08:00:00",
            "days_ago": 1,  # would put it near today — should be ignored
        }
        _insert_needle_emails(db, user, [needle], datetime.utcnow(), random)
        db.commit()

        msg = db.query(Message).filter_by(subject="Precedence test").one()
        assert msg.internal_date == datetime(2025, 3, 10, 8, 0, 0)

    def test_days_ago_still_works_without_received_at(self, db, user):
        now = datetime(2026, 3, 14, 12, 0, 0)
        needle = {
            "sender_name": "Sender",
            "sender_email": "s@example.com",
            "subject": "Days ago email",
            "body_plain": "body",
            "labels": ["INBOX"],
            "days_ago": 10,
        }
        _insert_needle_emails(db, user, [needle], now, random)
        db.commit()

        msg = db.query(Message).filter_by(subject="Days ago email").one()
        # Should be ~10 days before now (with some hours offset from rng)
        delta = (now - msg.internal_date).days
        assert 9 <= delta <= 10

    def test_multiple_needles_mixed(self, db, user):
        needles = [
            {
                "sender_name": "A",
                "sender_email": "a@example.com",
                "subject": "Absolute",
                "body_plain": "body",
                "labels": ["INBOX"],
                "received_at": "2025-02-01T12:00:00",
            },
            {
                "sender_name": "B",
                "sender_email": "b@example.com",
                "subject": "Relative",
                "body_plain": "body",
                "labels": ["INBOX"],
                "days_ago": 5,
            },
        ]
        now = datetime(2026, 3, 14, 12, 0, 0)
        _insert_needle_emails(db, user, needles, now, random)
        db.commit()

        absolute_msg = db.query(Message).filter_by(subject="Absolute").one()
        assert absolute_msg.internal_date == datetime(2025, 2, 1, 12, 0, 0)

        relative_msg = db.query(Message).filter_by(subject="Relative").one()
        delta = (now - relative_msg.internal_date).days
        assert 4 <= delta <= 5
