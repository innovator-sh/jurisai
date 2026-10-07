"""Sprint 5: account.html/settings.html/legal.html stopped being stubs (or,
for legal.html, didn't exist yet), and index.html/login.html were rebuilt on
base.html. These just confirm each route renders without a Jinja error --
the real client-side behaviour (chat.js, account.js, settings.js, login.js)
isn't exercised by TestClient, which doesn't run JS."""


def test_chat_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # The old inline <script> was a real, silent CSP violation (default-src
    # 'self', no 'unsafe-inline') -- pin that it's gone for good.
    assert "<script>" not in response.text


def test_account_page_renders(client):
    response = client.get("/account")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_settings_page_renders(client):
    response = client.get("/settings")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_legal_templates_page_renders(client):
    response = client.get("/templates")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_legal_templates_page_does_not_link_to_firform(client):
    """The FIR feature is blocked this sprint -- the page must not offer a
    live link to a route that doesn't exist."""
    response = client.get("/templates")
    assert "/firform" not in response.text
