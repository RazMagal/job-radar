"""The rendered page embeds third-party job data inside an inline <script> block —
these pin the escaping that keeps hostile titles from breaking out of it."""

from jobradar.report import render_html


def test_script_close_cannot_break_out():
    html = render_html([{"title": "sneaky</script><b>x</b>"}], {})
    assert "sneaky</script>" not in html


def test_double_escaped_state_trick_cannot_blank_page():
    # "<!--" + "<script" (no slash) puts the HTML tokenizer into the script-data
    # double-escaped state, so the template's real </script> stops closing the block.
    html = render_html([{"title": "Engineer <!--<script>"}], {})
    assert "<!--<script" not in html


def test_line_separators_do_not_reach_js_source():
    html = render_html([{"title": "a\u2028b\u2029c"}], {})
    assert "\u2028" not in html and "\u2029" not in html


def test_payload_still_valid_json():
    import json
    import re

    title = 'we<ird "title" </script>   &amp;'
    html = render_html([{"title": title}], {})
    # The jobs payload is a JSON array literal; recover it and round-trip it.
    m = re.search(r"JOBS\s*=\s*(\[.*?\]);", html, re.S)
    assert m, "could not locate the jobs array in the rendered page"
    assert json.loads(m.group(1))[0]["title"] == title
