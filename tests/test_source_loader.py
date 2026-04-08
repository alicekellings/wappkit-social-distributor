from app.source_loader import _clean_title, _clean_webpage_markdown, _parse_frontmatter


def test_clean_webpage_markdown_trims_shell_and_product_card() -> None:
    blocks = [
        "Wappkit Blog",
        "# Demo Post",
        "Article context",
        "Read the guide inside the same Wappkit surface as the product.",
        "Authors",
        "Wappkit Team",
        "# Demo Post",
        "Intro paragraph",
        "## Main Section",
        "Useful detail",
        "From Wappkit",
        "Reddit Toolbox",
        "View Product",
    ]

    cleaned = _clean_webpage_markdown(blocks, "Demo Post")

    assert cleaned.startswith("# Demo Post")
    assert "Intro paragraph" in cleaned
    assert "Useful detail" in cleaned
    assert "Article context" not in cleaned
    assert "From Wappkit" not in cleaned
    assert "View Product" not in cleaned


def test_clean_webpage_markdown_uses_first_title_when_only_one_exists() -> None:
    blocks = [
        "# Demo Post",
        "Intro paragraph",
        "## Section",
        "Useful detail",
    ]

    cleaned = _clean_webpage_markdown(blocks, "Demo Post")

    assert cleaned == "# Demo Post\n\nIntro paragraph\n\n## Section\n\nUseful detail"


def test_clean_title_removes_site_suffix() -> None:
    assert _clean_title("Demo Post | Wappkit Blog") == "Demo Post"


def test_parse_frontmatter_accepts_utf8_bom() -> None:
    raw = (
        '\ufeff---\n'
        'title: "Demo Post"\n'
        'description: "Demo description"\n'
        '---\n'
        '\n'
        'Body paragraph.\n'
    )

    metadata, body = _parse_frontmatter(raw)

    assert metadata["title"] == "Demo Post"
    assert metadata["description"] == "Demo description"
    assert body == "Body paragraph."
