"""Demo evaluation tasks for local debugging."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Task
from .registry import register_task


@dataclass
class FindDocument(Task):
    """Find a specific document by title."""

    name: str = "find-document"
    description: str = "Find a document by its title and read its content"
    instruction: str = "Find the document titled 'API v2 Migration Plan' and tell me what the timeline is."
    category: str = "capability"
    scenario: str = "default"
    tags: list[str] = field(default_factory=lambda: ["search", "read"])

    def evaluate(self, final_state, diff, action_log):
        # Check if any GET request targeted documents with a search query
        searched = any(
            "q=" in entry.get("path", "")
            for entry in action_log
            if entry.get("method") == "GET"
        )
        # Check if specific document was accessed
        doc_accessed = any(
            "/documents/" in entry.get("path", "") and entry.get("method") == "GET"
            for entry in action_log
        )

        reward = 0.0
        if searched:
            reward += 0.3
        if doc_accessed:
            reward += 0.7

        return reward, True


@dataclass
class CreateDocument(Task):
    """Create a new document with content."""

    name: str = "create-document"
    description: str = "Create a new document with specific content"
    instruction: str = "Create a new document called 'Weekly Summary' with a brief summary of recent meeting notes."
    category: str = "capability"
    scenario: str = "default"
    tags: list[str] = field(default_factory=lambda: ["create", "write"])

    def evaluate(self, final_state, diff, action_log):
        # Check if a document was created
        docs_added = []
        for user_data in diff.get("updated", {}).values():
            docs_added.extend(user_data.get("documents", {}).get("added", []))

        if not docs_added:
            return 0.0, True

        # Check title
        has_correct_title = any(
            "weekly" in d.get("title", "").lower() and "summary" in d.get("title", "").lower()
            for d in docs_added
        )

        reward = 0.3  # Created a document
        if has_correct_title:
            reward += 0.7

        return reward, True


register_task(FindDocument())
register_task(CreateDocument())
