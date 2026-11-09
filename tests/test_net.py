"""The packaged app must trust the certificates it carries (see net.py)."""
import os
import ssl

import certifi

from seeksync import net


def test_uses_certifi_when_nothing_usable_is_set(monkeypatch, tmp_path):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    assert net.use_bundled_certificates() == certifi.where()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()
    # a path that doesn't exist (the cert folder of the build machine) is replaced too
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    assert net.use_bundled_certificates() == certifi.where()
    assert os.environ["SSL_CERT_FILE"] == certifi.where()


def test_a_file_the_user_chose_is_respected(monkeypatch, tmp_path):
    mine = tmp_path / "mine.pem"
    mine.write_text("x")
    monkeypatch.setenv("SSL_CERT_FILE", str(mine))
    assert net.use_bundled_certificates() == ""
    assert os.environ["SSL_CERT_FILE"] == str(mine)


def test_ssl_contexts_then_load_the_bundle(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/cert.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "/nonexistent")
    net.use_bundled_certificates()
    ctx = ssl.create_default_context()
    assert ctx.cert_store_stats()["x509_ca"] > 50          # real root certificates, not an empty store


def test_importing_the_package_sets_it_up():
    import seeksync
    assert seeksync._use_bundled_certificates is net.use_bundled_certificates
