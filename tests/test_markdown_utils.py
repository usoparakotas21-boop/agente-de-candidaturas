from app.markdown_utils import markdown_to_plain_text


def test_markdown_plain_text_removes_syntax_for_speech():
    value = markdown_to_plain_text("# **Analista**\n- Resultado com [link](https://example.com)\n`código`")
    assert value == "Analista Resultado com link código"
    assert "*" not in value
    assert "#" not in value
    assert "https://" not in value

