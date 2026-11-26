"""서버 인가 코드 흐름: authorize → 제공자 → callback → 앱 딥링크(1회용 코드) → /api/auth/token."""
from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import select

from app.auth import pkce
from app.auth.models import OAuthAuthorize

from conftest import APP_CB, GOOGLE_WEB, bearer, query, run_db

VERIFIER = pkce.new_verifier()
CHALLENGE = pkce.s256(VERIFIER)


def authorize(client, provider="fake", **over):
    params = {"redirect_uri": APP_CB, "state": "app-st-1", "code_challenge": CHALLENGE,
              "code_challenge_method": "S256", "device_id": "dev-1", **over}
    params = {k: v for k, v in params.items() if v is not None}
    return client.get(f"/api/auth/{provider}/authorize", params=params)


def follow(client, url: str):
    """우리 서버 주소면 따라간다 (테스트 클라이언트는 자동으로 따라가지 않게 해 두었다)."""
    p = urlparse(url)
    return client.get(p.path + ("?" + p.query if p.query else ""))


def fake_login(client, **over) -> dict:
    """authorize → (가짜 제공자) → callback 까지. 앱 딥링크 쿼리를 돌려준다."""
    r = authorize(client, **over)
    assert r.status_code == 302, r.text
    cb = follow(client, r.headers["location"])
    assert cb.status_code == 302
    loc = cb.headers["location"]
    assert loc.startswith(over.get("redirect_uri", APP_CB) + "?")
    return query(loc)


def exchange(client, code, verifier=VERIFIER, redirect_uri=APP_CB):
    return client.post("/api/auth/token", json={"grantType": "authorization_code", "code": code,
                                                "codeVerifier": verifier, "redirectUri": redirect_uri})


def test_full_flow_with_fake_provider(client):
    q = fake_login(client)
    assert q["state"] == "app-st-1" and "accessToken" not in q and len(q["code"]) >= 40
    r = exchange(client, q["code"])
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["isNewUser"] is True and t["user"]["providers"] == ["FAKE"]
    assert client.get("/probe/me", headers=bearer(t)).status_code == 200
    row = run_db(lambda s: s.scalar(select(OAuthAuthorize)))
    assert row.state_hash != q["state"] and row.login_code_hash != q["code"]  # 원문은 두지 않는다
    assert row.device_id == "dev-1" and row.consumed_at is not None


def test_state_is_single_use(client):
    r = authorize(client)
    provider_url = r.headers["location"]
    assert "code" in query(follow(client, provider_url).headers["location"])
    again = query(follow(client, provider_url).headers["location"])  # 같은 state 로 다시
    assert again["error"] == "login_failed" and again["reason"] == "invalid_state"


def test_unknown_or_missing_state(client):
    for path in ("/api/auth/fake/callback?code=x&state=forged", "/api/auth/fake/callback?code=x"):
        loc = client.get(path).headers["location"]
        assert loc.startswith(APP_CB) and query(loc)["reason"] == "invalid_state"


def test_expired_state(client, env):
    env.set(OAUTH_STATE_TTL_S=0)
    r = authorize(client)
    q = query(follow(client, r.headers["location"]).headers["location"])
    assert q["reason"] == "invalid_state" and q["state"] == "app-st-1"


def test_redirect_uri_must_be_allowlisted(client):
    r = authorize(client, redirect_uri="https://evil.example/cb")
    assert r.status_code == 400 and "location" not in r.headers
    assert r.json()["error"]["code"] == "invalid_redirect_uri"
    # 허용 목록의 두 번째 주소(웹)는 된다
    assert fake_login(client, redirect_uri="http://localhost:5000/auth/callback")["code"]


def test_pkce_required_from_app(client):
    for over in ({"code_challenge": None}, {"code_challenge_method": "plain"}, {"code_challenge_method": None},
                 {"code_challenge": "too-short"}):
        r = authorize(client, **over)
        assert r.status_code == 302
        q = query(r.headers["location"])
        assert r.headers["location"].startswith(APP_CB) and q["reason"] == "invalid_code_challenge"


def test_wrong_verifier_burns_code(client):
    q = fake_login(client)
    r = exchange(client, q["code"], verifier=pkce.new_verifier())
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_grant"
    assert exchange(client, q["code"]).status_code == 400  # 맞는 verifier 로도 이제 안 된다


def test_wrong_redirect_uri_at_token(client):
    q = fake_login(client)
    assert exchange(client, q["code"], redirect_uri="http://localhost:5000/auth/callback").status_code == 400


def test_code_replay_revokes_issued_session(client):
    q = fake_login(client)
    t = exchange(client, q["code"]).json()
    assert exchange(client, q["code"]).status_code == 400
    assert client.get("/probe/me", headers=bearer(t)).json()["error"]["code"] == "session_revoked"


def test_expired_login_code(client, env):
    env.set(LOGIN_CODE_TTL_S=0)
    q = fake_login(client)
    assert exchange(client, q["code"]).status_code == 400


def test_provider_cancel(client):
    r = authorize(client)
    state = query(r.headers["location"])["state"]
    loc = client.get("/api/auth/fake/callback", params={"state": state, "error": "access_denied"}).headers["location"]
    q = query(loc)
    assert q["reason"] == "cancelled" and q["state"] == "app-st-1" and q["message"] == "로그인을 취소했어요."


def test_state_bound_to_provider(client):
    r = authorize(client)
    state = query(r.headers["location"])["state"]
    loc = client.get("/api/auth/google/callback", params={"state": state, "code": "x"}).headers["location"]
    assert query(loc)["reason"] == "invalid_state"


def test_google_server_flow(client, http):
    r = authorize(client, "google")
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    gq = query(loc)
    assert gq["client_id"] == GOOGLE_WEB and gq["code_challenge_method"] == "S256"
    assert gq["redirect_uri"] == "http://testserver/api/auth/google/callback"
    assert gq["scope"] == "openid email profile" and gq["nonce"] and gq["state"] != "app-st-1"
    assert gq["code_challenge"] != CHALLENGE  # 제공자용 PKCE 는 서버가 따로 만든다

    http.google_code = {"code": "g-code", "challenge": gq["code_challenge"], "nonce": gq["nonce"]}
    cb = client.get("/api/auth/google/callback", params={"code": "g-code", "state": gq["state"]})
    q = query(cb.headers["location"])
    assert "code" in q, q
    token_req = http.hits("/token")[0]
    assert b"client_secret=google-secret" in token_req.content and b"code_verifier=" in token_req.content
    t = exchange(client, q["code"]).json()
    assert t["user"]["providers"] == ["GOOGLE"] and t["user"]["email"] == "grandma@example.com"


def test_google_server_flow_nonce_mismatch(client, http):
    gq = query(authorize(client, "google").headers["location"])
    http.google_code = {"code": "g-code", "challenge": gq["code_challenge"], "nonce": "attacker-nonce"}
    q = query(client.get("/api/auth/google/callback", params={"code": "g-code", "state": gq["state"]}).headers["location"])
    assert q["error"] == "login_failed" and q["reason"] == "id_token_bad_nonce"


def test_kakao_server_flow(client, http):
    loc = authorize(client, "kakao").headers["location"]
    assert loc.startswith("https://kauth.kakao.com/oauth/authorize?")
    kq = query(loc)
    assert kq["client_id"] == "kakao-rest-key" and kq["code_challenge_method"] == "S256"
    assert kq["redirect_uri"] == "http://testserver/api/auth/kakao/callback"

    http.kakao_code = {"code": "k-code", "challenge": kq["code_challenge"], "token": "kakao-good"}
    q = query(client.get("/api/auth/kakao/callback", params={"code": "k-code", "state": kq["state"]}).headers["location"])
    req = http.hits("/oauth/token")[0]
    assert b"client_secret=kakao-secret" in req.content
    t = exchange(client, q["code"]).json()
    assert t["user"]["providers"] == ["KAKAO"] and t["user"]["name"] == "박영감"


def test_kakao_code_rejected_redirects_with_reason(client, http):
    kq = query(authorize(client, "kakao").headers["location"])
    q = query(client.get("/api/auth/kakao/callback", params={"code": "bad", "state": kq["state"]}).headers["location"])
    assert q["reason"] == "kakao_code_rejected" and q["provider"] == "kakao"


def test_provider_not_configured_redirects_to_app(client, env):
    env.mp.delenv("GOOGLE_CLIENT_SECRET")
    env.set()
    r = authorize(client, "google")
    assert r.status_code == 302 and query(r.headers["location"])["reason"] == "google_not_configured"
