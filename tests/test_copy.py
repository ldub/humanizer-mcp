import pytest
from pydantic import ValidationError

from humanizer_mcp.copy import CopyField, RewriteRequest, rewrite_field, validate


@pytest.mark.parametrize(
    ("original", "candidate", "warning"),
    [
        ("37 complaints", "37% complaints", "numbers_changed"),
        ("It costs $19", "It costs $29", "numbers_changed"),
        ("Run `npm test`", "Run `npm run test`", "protected_content_changed"),
        ("Visit https://example.com", "Visit https://example.org", "protected_content_changed"),
        ("Hello {first_name}", "Hello {name}", "protected_content_changed"),
        ('They said "keep it"', 'They said "change it"', "protected_content_changed"),
    ],
)
def test_mechanical_changes_are_rejected(original, candidate, warning):
    assert warning in validate(original, candidate)


def test_names_are_preserved_when_declared():
    assert "required_terms_changed" in validate("Contact Alex Chen", "Contact Alex", preserve=["Alex Chen"])


def test_truncation_retains_original():
    field = CopyField(id="body", text="This is our complete message.")
    result = rewrite_field(field, lambda _: {"text": "This is", "truncated": True})
    assert result["text"] == field.text
    assert result["status"] == "original_retained"


def test_character_limit_falls_back_instead_of_truncating():
    field = CopyField(id="button", text="Save", max_characters=8)
    result = rewrite_field(field, lambda _: {"text": "Save all changes"})
    assert result["text"] == "Save"
    assert "character_limit_exceeded" in result["warnings"]


def test_markdown_structure_kept_while_prose_changes():
    draft = '# Welcome\n\nWe utilize useful tools.\n\n- You can utilize this.\n\n```py\nprint("utilize")\n```\n\n> Exact quotation\n'
    field = CopyField(id="page", text=draft, format="markdown")
    result = rewrite_field(field, lambda text: {"text": text.replace("utilize", "use")})
    assert result["status"] == "rewritten"
    assert "# Welcome\n" in result["text"]
    assert "- You can use this." in result["text"]
    assert 'print("utilize")' in result["text"]
    assert "> Exact quotation\n" in result["text"]


def test_invalid_batch_is_rejected_before_inference():
    with pytest.raises(ValidationError):
        RewriteRequest(fields=[{"id": "a", "text": "one"}, {"id": "a", "text": "two"}])
    with pytest.raises(ValidationError):
        CopyField(id="a", text="one", preserve=["missing"])


def test_long_text_is_chunked():
    calls = []
    draft = " ".join(["We utilize helpful tools every single day."] * 120)

    def generate(text):
        calls.append(text)
        return {"text": text.replace("utilize", "use")}

    result = rewrite_field(CopyField(id="long", text=draft), generate)
    assert len(calls) > 1
    assert result["status"] == "rewritten"
    assert result["text"].count("We use helpful tools every single day.") == 120
