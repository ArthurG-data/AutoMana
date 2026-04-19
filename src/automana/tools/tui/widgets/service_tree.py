"""
ServiceTree — a collapsible Textual Tree grouped by domain prefix.

Each leaf node stores the full dot-separated service key as its data.
"""

from __future__ import annotations

from collections import defaultdict

from textual.widgets import Tree
from textual.widgets.tree import TreeNode


class ServiceTree(Tree[str]):
    """Collapsible tree of registered services grouped by top-level domain."""

    DEFAULT_CSS = """
    ServiceTree {
        width: 1fr;
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """

    def populate(self, service_keys: list[str]) -> None:
        """Build the tree from a list of dot-separated service keys."""
        self.clear()
        groups: dict[str, list[str]] = defaultdict(list)
        for key in sorted(service_keys):
            domain = key.split(".")[0]
            groups[domain].append(key)

        for domain, keys in sorted(groups.items()):
            branch = self.root.add(domain, expand=False)
            for key in keys:
                # Label shows the tail (after the first dot), data is the full key
                label = key[len(domain) + 1:]
                branch.add_leaf(label, data=key)

        self.root.expand()
