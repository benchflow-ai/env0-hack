"""Tests that _read_task_config reads GCAL_FILL_CONFIG from needles modules."""

from __future__ import annotations

import types

from unittest import mock

from mock_gcal.seed.task_seed import _read_task_config


def _make_needles_module(**attrs) -> types.ModuleType:
    mod = types.ModuleType("fake_needles")
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


class TestGcalFillConfig:
    def test_reads_gcal_fill_config(self):
        mod = _make_needles_module(
            GCAL_FILL_CONFIG={"target_count": 35},
            NEEDLE_EVENTS=[{"summary": "e1"}],
        )
        with mock.patch("mock_gcal.seed.task_seed._load_needles_module", return_value=mod):
            _, _, fill_config = _read_task_config("fake-task")
        assert fill_config == {"target_count": 35}

    def test_empty_without_gcal_fill_config(self):
        mod = _make_needles_module(NEEDLE_EVENTS=[])
        with mock.patch("mock_gcal.seed.task_seed._load_needles_module", return_value=mod):
            _, _, fill_config = _read_task_config("fake-task")
        assert fill_config == {}

    def test_ignores_plain_fill_config(self):
        mod = _make_needles_module(
            FILL_CONFIG={"target_count": 999},
            NEEDLE_EVENTS=[],
        )
        with mock.patch("mock_gcal.seed.task_seed._load_needles_module", return_value=mod):
            _, _, fill_config = _read_task_config("fake-task")
        assert fill_config == {}
