"""Install alongside supply_workbench_static in key_test.demand_collaboration.

Returns parts of the same fixed, private generated artifact using the existing
System Manager authorization. No path arguments, remote requests or writes.
"""
from __future__ import annotations

import re

from .supply_workbench_static import _whitelist, get_html


def split_parts(markup: str) -> dict[str, str]:
    """Split our generated HTML, preserving the inert JSON data script."""
    styles = re.findall(r"<style>(.*?)</style>", markup, re.S)
    bodies = re.findall(r"<body>(.*?)</body>", markup, re.S)
    scripts = re.findall(r"<script>(.*?)</script>", markup, re.S)
    if len(styles) != 1 or len(bodies) != 1 or len(scripts) != 1:
        raise ValueError("Expected one generated workbench style, body and executable script")
    body = re.sub(r"<script>.*?</script>", "", bodies[0], flags=re.S)
    return {"html": body, "css": styles[0], "js": scripts[0]}


@_whitelist
def get_parts():
    """Read-only native Page bridge; get_html enforces login and role checks."""
    return split_parts(get_html())
