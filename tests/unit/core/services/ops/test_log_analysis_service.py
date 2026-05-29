from automana.core.services.ops.log_analysis_service import (
    extract_error_lines,
    build_claude_prompt,
    format_discord_message,
)


def _loki_response(lines: list) -> dict:
    return {
        "data": {
            "result": [
                {
                    "stream": {"container": "automana-backend-dev", "level": "ERROR"},
                    "values": [[str(i * 1_000_000_000), line] for i, line in enumerate(lines)],
                }
            ]
        }
    }


def test_extract_error_lines_returns_log_strings():
    resp = _loki_response([
        '{"level":"ERROR","msg":"db connection failed","logger":"automana.db"}',
        '{"level":"ERROR","msg":"task retry exceeded","logger":"automana.worker"}',
    ])
    lines = extract_error_lines(resp)
    assert len(lines) == 2
    assert "db connection failed" in lines[0]


def test_extract_error_lines_empty_result():
    resp = {"data": {"result": []}}
    assert extract_error_lines(resp) == []


def test_build_claude_prompt_includes_lines():
    lines = ["ERROR: db failed", "ERROR: task timeout"]
    prompt = build_claude_prompt(lines, window_hours=24)
    assert "db failed" in prompt
    assert "24" in prompt


def test_build_claude_prompt_truncates_at_500_lines():
    lines = [f"ERROR: line {i}" for i in range(600)]
    prompt = build_claude_prompt(lines, window_hours=24)
    assert "line 499" in prompt
    assert "line 500" not in prompt


def test_format_discord_message_includes_count():
    msg = format_discord_message("Summary here.", error_count=42, window_hours=24)
    assert "42" in msg
    assert "Summary here." in msg
