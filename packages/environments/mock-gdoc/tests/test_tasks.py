"""Task registration tests for mock-gdoc."""

from __future__ import annotations


def test_list_tasks_includes_demo_tasks():
    from mock_gdoc.tasks import list_tasks

    tasks = set(list_tasks())

    assert "find-document" in tasks
    assert "create-document" in tasks


def test_get_demo_task_metadata():
    from mock_gdoc.tasks import get_task

    task = get_task("find-document")

    assert task is not None
    assert task.category == "capability"
