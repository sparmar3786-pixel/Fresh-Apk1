from backend.app.angel import resolve_totp


def test_resolve_totp_accepts_current_six_digit_code():
    assert resolve_totp("123456") == "123456"


def test_resolve_totp_rejects_missing_code():
    try:
        resolve_totp(None)
    except RuntimeError as exc:
        assert "6-digit TOTP is required" in str(exc)
    else:
        raise AssertionError("Expected missing TOTP to fail")


def test_resolve_totp_rejects_non_six_digit_code():
    try:
        resolve_totp("12345")
    except RuntimeError as exc:
        assert "exactly 6 digits" in str(exc)
    else:
        raise AssertionError("Expected invalid TOTP to fail")


def test_connect_rejects_status_false_even_if_http_request_returns(monkeypatch):
    import sys
    import types
    from backend.app.angel import AngelGateway

    class FakeSmartConnect:
        access_token = None
        refresh_token = None

        def __init__(self, api_key):
            self.api_key = api_key

        def generateSession(self, client_code, pin, totp):
            return {"status": False, "message": "Invalid TOTP", "errorcode": "AB1050"}

    fake_module = types.ModuleType("SmartApi")
    fake_module.SmartConnect = FakeSmartConnect
    monkeypatch.setitem(sys.modules, "SmartApi", fake_module)

    gateway = AngelGateway()
    try:
        gateway.connect("api-key", "client", "1234", "123456")
    except RuntimeError as exc:
        assert "AB1050" in str(exc)
    else:
        raise AssertionError("A status=false login response must fail")
    assert gateway.authenticated is False
    assert gateway.auth_token is None
    assert gateway.feed_token is None


def test_connect_requires_jwt_and_feed_token_before_authentication(monkeypatch):
    import sys
    import types
    from backend.app.angel import AngelGateway

    class FakeSmartConnect:
        access_token = None
        refresh_token = None

        def __init__(self, api_key):
            self.api_key = api_key

        def generateSession(self, client_code, pin, totp):
            return {"status": True, "message": "Login successful", "data": {"jwtToken": "jwt-only"}}

        def getfeedToken(self):
            return None

        def setAccessToken(self, token):
            self.access_token = token

    fake_module = types.ModuleType("SmartApi")
    fake_module.SmartConnect = FakeSmartConnect
    monkeypatch.setitem(sys.modules, "SmartApi", fake_module)

    gateway = AngelGateway()
    try:
        gateway.connect("api-key", "client", "1234", "123456")
    except RuntimeError as exc:
        assert "feedToken" in str(exc)
    else:
        raise AssertionError("Missing feedToken must fail authentication")
    assert gateway.authenticated is False
