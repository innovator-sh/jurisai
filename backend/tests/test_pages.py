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


_PAGES = ["/login", "/", "/account", "/settings", "/templates", "/privacy"]


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


def test_privacy_page_renders_both_languages_and_is_public(client):
    """It is linked from the signup form, so it must load logged-out."""
    response = client.get("/privacy")
    assert response.status_code == 200
    assert 'id="english"' in response.text and 'id="hindi"' in response.text
    assert "गोपनीयता सूचना" in response.text
    assert "Grievance Officer" in response.text and "शिकायत अधिकारी" in response.text


def test_privacy_page_shows_the_configured_grievance_officer(client, monkeypatch):
    settings = client.app.state.settings
    monkeypatch.setattr(settings, "grievance_officer_name", "A. Officer")
    monkeypatch.setattr(settings, "grievance_officer_email", "grievance@example.in")
    monkeypatch.setattr(settings, "grievance_officer_address", "1 Example Road, Pune")
    html = client.get("/privacy").text
    assert "A. Officer" in html
    assert 'href="mailto:grievance@example.in"' in html
    assert "1 Example Road, Pune" in html


def test_privacy_page_states_the_real_retention_and_log_periods(client, monkeypatch):
    monkeypatch.setattr(client.app.state.settings, "chat_retention_days", 90)
    html = client.get("/privacy").text
    assert "after 90 days" in html
    assert "180 days, on a server located in India" in html


def test_privacy_page_names_who_receives_the_question_text(client):
    """The AI provider is a real recipient of the user's question; naming it
    is a disclosure requirement, so it must track the configured provider."""
    assert "Groq" in client.get("/privacy").text


def test_privacy_page_escapes_configured_values(client, monkeypatch):
    monkeypatch.setattr(
        client.app.state.settings, "grievance_officer_name", "<script>alert(1)</script>"
    )
    html = client.get("/privacy").text
    assert "<script>alert(1)</script>" not in html


def test_signup_form_asks_for_role_and_consent_and_links_the_notice(client):
    html = client.get("/login").text
    assert 'id="role"' in html and 'id="consent"' in html
    assert 'href="/privacy"' in html


@pytest.mark.parametrize("path", _PAGES)
def test_every_page_links_a_favicon_that_exists(client, path):
    """Without a <link rel=icon> every page load makes the browser request
    /favicon.ico, a guaranteed 404 in the console and the access log."""
    assert 'rel="icon"' in client.get(path).text
    icon = client.get("/static/favicon.svg")
    assert icon.status_code == 200
    assert "svg" in icon.headers["content-type"]
