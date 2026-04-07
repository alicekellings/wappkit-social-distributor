from app.store import DeliveryStore


def test_store_success_roundtrip(tmp_path) -> None:
    store = DeliveryStore(tmp_path / "state.sqlite3")
    store.mark_attempt(
        platform="devto",
        source_slug="demo-post",
        source_url="https://www.wappkit.com/blog/demo-post",
        title="Demo Post",
        source_updated_at="2026-04-07T00:00:00Z",
    )
    assert store.has_success("devto", "demo-post") is False

    store.mark_success(
        platform="devto",
        source_slug="demo-post",
        external_id="123",
        external_url="https://dev.to/example/demo-post",
    )

    assert store.has_success("devto", "demo-post") is True
