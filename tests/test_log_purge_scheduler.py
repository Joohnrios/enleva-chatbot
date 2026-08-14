"""Testes do cálculo de espera do agendador de purge."""

from datetime import datetime, timezone

from backend.app.security.log_purge_scheduler import seconds_until_next_purge


def test_seconds_until_next_purge_same_day():
    now = datetime(2026, 8, 8, 1, 0, 0, tzinfo=timezone.utc)
    wait = seconds_until_next_purge(3, now=now)
    assert abs(wait - 2 * 3600) < 1


def test_seconds_until_next_purge_rolls_to_next_day():
    now = datetime(2026, 8, 8, 4, 0, 0, tzinfo=timezone.utc)
    wait = seconds_until_next_purge(3, now=now)
    assert abs(wait - 23 * 3600) < 1
