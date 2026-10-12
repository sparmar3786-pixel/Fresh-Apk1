from cryptography.fernet import Fernet

from backend.app import secure_store


def test_angel_session_saves_pin_and_tokens_encrypted(tmp_path, monkeypatch):
    monkeypatch.setattr(secure_store, "DB_PATH", tmp_path / "secure.db")
    monkeypatch.setenv("APP_FERNET_KEY", Fernet.generate_key().decode())
    secure_store.init_store()

    secure_store.save_angel_session(
        "device-test",
        client_code="client-123",
        api_key="api-key-secret",
        pin="2468",
        jwt="jwt-secret",
        refresh="refresh-secret",
        feed="feed-secret",
    )

    session = secure_store.load_angel_session("device-test")
    assert session["client_code"] == "client-123"
    assert session["api_key"] == "api-key-secret"
    assert session["pin"] == "2468"
    assert session["jwt"] == "jwt-secret"
    assert session["refresh"] == "refresh-secret"
    assert session["feed"] == "feed-secret"

    with secure_store.connect() as conn:
        raw = conn.execute(
            "SELECT api_key_enc, pin_enc, jwt_enc, refresh_enc, feed_enc "
            "FROM angel_sessions WHERE device_id = ?",
            ("device-test",),
        ).fetchone()
    assert "2468" not in str(tuple(raw))
    assert "jwt-secret" not in str(tuple(raw))


def test_init_store_migrates_existing_angel_sessions_table(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setattr(secure_store, "DB_PATH", tmp_path / "old.db")
    monkeypatch.setenv("APP_FERNET_KEY", Fernet.generate_key().decode())
    with sqlite3.connect(secure_store.DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE angel_sessions ("
            "device_id TEXT PRIMARY KEY, client_code TEXT NOT NULL, "
            "api_key_enc TEXT NOT NULL, jwt_enc TEXT NOT NULL, "
            "refresh_enc TEXT, feed_enc TEXT, updated_at TEXT NOT NULL)"
        )

    secure_store.init_store()
    with secure_store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(angel_sessions)")}
    assert "pin_enc" in columns


def test_init_store_migrates_existing_ai_credentials_table(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setattr(secure_store, "DB_PATH", tmp_path / "legacy-ai.db")
    monkeypatch.setenv("APP_FERNET_KEY", Fernet.generate_key().decode())
    with sqlite3.connect(secure_store.DB_PATH) as conn:
        conn.execute(
            "CREATE TABLE ai_credentials ("
            "device_id TEXT PRIMARY KEY, openai_key_enc TEXT, "
            "model TEXT NOT NULL DEFAULT 'gpt-5', updated_at TEXT NOT NULL)"
        )

    secure_store.init_store()
    with secure_store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(ai_credentials)")}
    assert {"exa_key_enc", "tavily_key_enc", "brave_key_enc"} <= columns

    secure_store.save_ai(
        "legacy-device",
        openai_key="openai-secret",
        model="gpt-5",
        exa_key="exa-secret",
        tavily_key="tavily-secret",
        brave_key="brave-secret",
    )
    loaded = secure_store.load_ai("legacy-device")
    assert loaded == {
        "openai_api_key": "openai-secret",
        "openai_model": "gpt-5",
        "exa_api_key": "exa-secret",
        "tavily_api_key": "tavily-secret",
        "brave_search_api_key": "brave-secret",
    }


def test_save_ai_preserves_existing_search_keys_when_fields_are_blank(tmp_path, monkeypatch):
    monkeypatch.setattr(secure_store, "DB_PATH", tmp_path / "secure.db")
    monkeypatch.setenv("APP_FERNET_KEY", Fernet.generate_key().decode())
    secure_store.init_store()
    secure_store.save_ai(
        "device-test",
        openai_key="openai-secret",
        model="gpt-5",
        exa_key="exa-secret",
        tavily_key="tavily-secret",
        brave_key="brave-secret",
    )

    secure_store.save_ai("device-test", openai_key=None, model="gpt-5")

    loaded = secure_store.load_ai("device-test")
    assert loaded == {
        "openai_api_key": "openai-secret",
        "openai_model": "gpt-5",
        "exa_api_key": "exa-secret",
        "tavily_api_key": "tavily-secret",
        "brave_search_api_key": "brave-secret",
    }
    with secure_store.connect() as conn:
        row = conn.execute(
            "SELECT exa_key_enc, tavily_key_enc, brave_key_enc "
            "FROM ai_credentials WHERE device_id=?",
            ("device-test",),
        ).fetchone()
    assert all(row)
