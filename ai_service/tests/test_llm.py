import json
import pytest
from ai_service.llm import parse_json, Model
from ai_service.models import Code, Credentials
from ai_service.journal import Journal


def test_literal_html_whitespace_and_cached_response(tmp_path):
    reply = '{"html":"<!DOCTYPE html>\n<html>\t<body>示例</body>\r\n</html>"}'
    journal = Journal(tmp_path / "calls.sqlite")
    journal.invoke(
        "run",
        "coder-0",
        50000,
        1000,
        lambda: {
            "content": reply,
            "inputTokens": 100,
            "outputTokens": 200,
            "usageKnown": True,
        },
    )
    model = Model(
        Credentials(baseUrl="https://www.dmxapi.cn/v1", model="test", apiKey="unused"),
        journal,
        "run",
        50000,
    )
    # The completed response is replayed from SQLite; no provider call is made.
    result = model.call("coder-0", "test", {}, Code)
    assert result["html"] == "<!DOCTYPE html>\n<html>\t<body>示例</body>\r\n</html>"
    assert journal.usage("run")["calls"] == 1
    assert journal.usage("run")["outputTokens"] == 200


def test_strict_structure_and_schema_remain_required():
    valid = {"html": "<!DOCTYPE html><html>示例</html>"}
    assert parse_json("```json\n" + json.dumps(valid) + "\n```", Code) == valid
    for invalid in [
        '{"html":"truncated',
        '{"html":"short"}',
        '{"html":"<!DOCTYPE html>\x00</html>"}',
        "plain HTML",
    ]:
        with pytest.raises(ValueError):
            parse_json(invalid, Code)


def test_html_transport_preserves_quotes_and_rejects_truncation():
    from ai_service.llm import parse_code

    html = '<!DOCTYPE html>\n<html><body class="card">Text</body></html>'
    assert parse_code(html)["html"] == html
    assert parse_code("```json\n" + json.dumps({"html": html}) + "\n```")["html"] == html
    assert parse_code("```html\n" + html + "\n```")["html"] == html
    for invalid in ["Explanation: " + html, html[:-7], "<div>partial</div>"]:
        with pytest.raises(ValueError):
            parse_code(invalid)
