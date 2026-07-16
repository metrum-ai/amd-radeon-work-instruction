# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Shared helpers for rendering the standard.html export template.

Both the HTML and PDF exporters render the same template, so the running-header
sanitization and CSS inlining live here to stay consistent across formats.
"""

import re
from pathlib import Path

# Characters that could break out of a CSS string literal or the enclosing
# <style> element (element-boundary breakout → XSS in the HTML export).
_CSS_UNSAFE = re.compile(r"""[<>"'\\&\r\n\t]""")


def running_header_safe(value: object) -> str:
    """Strip characters unsafe inside an inline ``<style>`` running header.

    The value is injected into a CSS ``content: "..."`` string, so ``<``/``>``
    (element breakout) and ``"``/``\\``/newlines (string breakout) are removed
    rather than HTML-escaped (HTML entities are invalid inside a CSS string).
    """
    return _CSS_UNSAFE.sub("", str(value if value is not None else ""))


def read_inline_css(templates_dir: str | Path) -> str:
    """Return the contents of print.css for inlining into the export.

    Inlining makes the HTML export self-contained (a relative ``<link>`` can't
    resolve once the file is opened standalone) and is honored by WeasyPrint for
    the PDF path. Returns ``""`` if the stylesheet is missing.
    """
    css_path = Path(templates_dir) / "print.css"
    try:
        return css_path.read_text(encoding="utf-8")
    except OSError:
        return ""
