"""Sprint 5: account.html/settings.html/legal.html stopped being stubs (or,
for legal.html, didn't exist yet), and index.html/login.html were rebuilt on
base.html. These just confirm each route renders without a Jinja error --
the real client-side behaviour (chat.js, account.js, settings.js, login.js)
isn't exercised by TestClient, which doesn't run JS."""

import re

import pytest


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


_PAGES = ["/login", "/", "/account", "/settings", "/templates"]


@pytest.mark.parametrize("path", _PAGES)
def test_pages_have_no_inline_style_or_handlers(client, path):
    """default-src 'self' blocks inline style="" attributes and on* handlers
    silently -- a hidden-by-inline-style element just shows up. Found for real
    by the Sprint 5 Lighthouse pass; pin it so it can't come back."""
    html = client.get(path).text
    assert not re.search(r"""\sstyle\s*=""", html), f"{path} has an inline style attribute"
    assert not re.search(r"""\son[a-z]+\s*=""", html), f"{path} has an inline event handler"


def test_sidebar_nav_items_are_real_links(client):
    """Nav items were <li role="link" tabindex="0"> -- invalid ARIA that
    Lighthouse flagged. They must be real anchors with an accessible name."""
    html = client.get("/").text
    assert 'role="link"' not in html
    assert "data-nav-href" not in html
    for href in ("/", "/templates", "/?view=history", "/account", "/settings"):
        assert re.search(rf'<a class="nav-link" href="{re.escape(href)}" aria-label="[^"]+"', html)
