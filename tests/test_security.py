import sys
sys.path.insert(0, ".")

from services.security import SecurityEngine, RateLimiter


def test_password_hash_verify():
    h, s = SecurityEngine.generate_hash("test_password")
    assert SecurityEngine.verify(h, s, "test_password")
    assert not SecurityEngine.verify(h, s, "wrong_password")


def test_password_min_length():
    assert SecurityEngine.valid_password("abcdef")
    assert not SecurityEngine.valid_password("abcde")


def test_token_generation():
    t1 = SecurityEngine.create_token()
    t2 = SecurityEngine.create_token()
    assert len(t1) == 64
    assert t1 != t2


def test_totp_secret_generation():
    secret = SecurityEngine.generate_totp_secret_b32()
    assert len(secret) >= 16
    assert secret.isalnum() or "+/=" in secret or secret.isascii()


def test_totp_uri_format():
    secret = SecurityEngine.generate_totp_secret_b32()
    uri = SecurityEngine.get_totp_uri(secret, "testuser", "TestApp")
    assert "otpauth://totp/" in uri
    assert "testuser" in uri
    assert secret in uri


def test_rate_limiter_basic():
    rl = RateLimiter()
    locked, remaining = rl.check_login("admin")
    assert not locked
    assert remaining == 0


def test_rate_limiter_lockout():
    rl = RateLimiter()
    for _ in range(5):
        rl.record_login("attacker")
    locked, remaining = rl.check_login("attacker")
    assert locked
    assert remaining > 0


def test_rate_limiter_clear():
    rl = RateLimiter()
    for _ in range(5):
        rl.record_login("user")
    rl.clear_login("user")
    locked, _ = rl.check_login("user")
    assert not locked
