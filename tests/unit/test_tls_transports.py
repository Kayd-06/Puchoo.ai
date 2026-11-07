"""Real local TLS handshakes, not external service connectivity tests.

Minimal protocol peers exercise smtplib, libpq/psycopg and PyMySQL with synthetic
certificates/credentials. They are not database engines and do not test SQL.
OpenSSL (available on the Ubuntu CI runner) creates ephemeral test certificates.
"""

from contextlib import contextmanager
import shutil
import socket
import ssl
import struct
import subprocess
import threading

import pytest
import psycopg
import pymysql
from sqlalchemy.exc import DBAPIError

from apps.core.db_connection import (
    checked_connection_host,
    connect_args_for,
    create_database_engine,
)
from apps.core.executor import ReadOnlyExecutor
from apps.core.workspaces import _open_engine
from backend import emailer

HOST = "tls-fixture.invalid"


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    if not shutil.which("openssl"):
        pytest.skip("local TLS fixtures require the OpenSSL command-line tool")
    directory = tmp_path_factory.mktemp("tls-certificates")

    def openssl(*args):
        subprocess.run(["openssl", *map(str, args)], cwd=directory, check=True,
                       capture_output=True, timeout=20)

    for name in ("ca", "other-ca"):
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                "-subj", f"/CN={name}", "-keyout", f"{name}.key", "-out", f"{name}.pem",
                "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    (directory / "index").write_text("")
    (directory / "serial").write_text("1000\n")
    (directory / "ca.cnf").write_text(
        "[ca]\ndefault_ca=local\n[local]\ndatabase=index\nnew_certs_dir=.\n"
        "certificate=ca.pem\nprivate_key=ca.key\nserial=serial\ndefault_md=sha256\n"
        "policy=policy\n[policy]\ncommonName=supplied\n"
    )
    for name, hostname, days in (("matching", HOST, 2), ("wrong-host", "other.invalid", 2),
                                 ("expired", HOST, -1)):
        openssl("req", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={hostname}",
                "-keyout", f"{name}.key", "-out", f"{name}.csr")
        (directory / "extensions").write_text(
            f"subjectAltName=DNS:{hostname}\nbasicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
            "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n"
        )
        if name == "expired":
            openssl("ca", "-batch", "-config", "ca.cnf", "-in", f"{name}.csr",
                    "-out", f"{name}.pem", "-startdate", "20200101000000Z",
                    "-enddate", "20200102000000Z", "-extfile", "extensions")
        else:
            openssl("x509", "-req", "-in", f"{name}.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
                    "-CAcreateserial", "-out", f"{name}.pem", "-days", days, "-extfile", "extensions")
    return directory


def _read_exact(stream, size):
    data = b""
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise EOFError("local peer disconnected")
        data += chunk
    return data


def _mysql_read(stream):
    header = _read_exact(stream, 4)
    return _read_exact(stream, int.from_bytes(header[:3], "little"))


def _mysql_write(stream, payload, sequence):
    stream.sendall(len(payload).to_bytes(3, "little") + bytes([sequence]) + payload)


@contextmanager
def local_peer(protocol, certificates, certificate="matching", supports_tls=True, connections=1):
    state = {"tls": False, "credentials": False, "errors": [], "sni": None, "connections": 0}
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(4)
    state["port"] = listener.getsockname()[1]
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificates / f"{certificate}.pem", certificates / f"{certificate}.key")
    context.set_servername_callback(lambda _socket, name, _context: state.update(sni=name))

    def upgrade(stream):
        stream = context.wrap_socket(stream, server_side=True)
        state["tls"] = True
        return stream

    def serve_one():
        stream = None
        try:
            stream, _ = listener.accept()
            state["connections"] += 1
            stream.settimeout(4)
            if protocol == "postgresql":
                assert _read_exact(stream, 8) == struct.pack("!II", 8, 80877103)
                stream.sendall(b"S" if supports_tls else b"N")
                if not supports_tls:
                    return
                stream = upgrade(stream)
                length = struct.unpack("!I", _read_exact(stream, 4))[0]
                _read_exact(stream, length - 4)  # Startup, sent only after certificate verification.
                state["credentials"] = True

                def message(kind, data):
                    return kind + struct.pack("!I", len(data) + 4) + data

                stream.sendall(message(b"R", struct.pack("!I", 0)) +
                               message(b"S", b"server_version\x0016.0\x00") +
                               message(b"S", b"client_encoding\x00UTF8\x00") +
                               message(b"S", b"standard_conforming_strings\x00on\x00") +
                               message(b"K", struct.pack("!II", 1, 2)) + message(b"Z", b"I"))
                stream.recv(1024)  # client close/Terminate
            elif protocol == "mysql":
                from pymysql.constants import CLIENT
                capabilities = (CLIENT.PROTOCOL_41 | CLIENT.SECURE_CONNECTION | CLIENT.PLUGIN_AUTH |
                                CLIENT.CONNECT_WITH_DB | CLIENT.TRANSACTIONS)
                if supports_tls:
                    capabilities |= CLIENT.SSL
                greeting = (b"\x0a8.0.36\x00" + struct.pack("<I", 1) + b"12345678\x00" +
                            struct.pack("<H", capabilities & 65535) + b"\x2d\x02\x00" +
                            struct.pack("<H", capabilities >> 16) + b"\x15" + b"\x00" * 10 +
                            b"abcdefghijkl\x00mysql_native_password\x00")
                _mysql_write(stream, greeting, 0)
                request = _mysql_read(stream)
                if not supports_tls:
                    state["credentials"] = True
                    return
                assert len(request) == 32  # SSLRequest contains no username/password.
                stream = upgrade(stream)
                _mysql_read(stream)
                state["credentials"] = True
                ok = b"\x00\x00\x00\x02\x00\x00\x00"
                _mysql_write(stream, ok, 3)
                while True:
                    command = _mysql_read(stream)
                    if command[:1] == b"\x01":  # COM_QUIT
                        break
                    _mysql_write(stream, ok, 1)  # SET NAMES / AUTOCOMMIT / ROLLBACK only.
            else:
                if protocol == "smtps":
                    stream = upgrade(stream)
                stream.sendall(b"220 fixture ESMTP\r\n")
                reader = stream.makefile("rb")
                in_data = False
                while True:
                    line = reader.readline()
                    if not line:
                        break
                    if in_data:
                        if line == b".\r\n":
                            in_data = False
                            stream.sendall(b"250 accepted\r\n")
                        continue
                    command = line.split(b" ", 1)[0].strip().upper()
                    if command in (b"EHLO", b"HELO"):
                        starttls = b"250-STARTTLS\r\n" if supports_tls else b""
                        stream.sendall(b"250-fixture\r\n" + starttls + b"250 AUTH PLAIN\r\n")
                    elif command == b"STARTTLS":
                        stream.sendall(b"220 ready\r\n")
                        reader.close()
                        stream = upgrade(stream)
                        reader = stream.makefile("rb")
                    elif command == b"AUTH":
                        state["credentials"] = True
                        stream.sendall(b"235 authenticated\r\n")
                    elif command == b"DATA":
                        stream.sendall(b"354 send data\r\n")
                        in_data = True
                    elif command == b"QUIT":
                        stream.sendall(b"221 bye\r\n")
                        break
                    else:
                        stream.sendall(b"250 ok\r\n")
                reader.close()
        except (OSError, EOFError) as exc:
            state["errors"].append(type(exc).__name__)
        finally:
            if stream is not None:
                stream.close()

    def serve():
        for _ in range(connections):
            serve_one()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        listener.close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "local protocol peer must not hang"


@pytest.mark.parametrize("protocol", ["postgresql", "mysql"])
@pytest.mark.parametrize("case", ["matching", "wrong-host", "untrusted", "expired"])
def test_database_real_driver_verifies_original_hostname_and_checked_ip(monkeypatch, certificates, protocol, case):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DB_SSL_REQUIRED", "true")
    monkeypatch.setenv("DB_SSL_MODE", "verify-full")
    ca = str(certificates / ("other-ca.pem" if case == "untrusted" else "ca.pem"))
    monkeypatch.setenv("DB_SSL_CA", ca)
    monkeypatch.setenv("DB_SSL_ROOT_CERT", ca)
    monkeypatch.setenv("ALLOWED_DB_HOSTS", HOST)
    actual_resolver = socket.getaddrinfo
    lookups = []

    def resolve_once(host, port, *args, **kwargs):
        if host == HOST:
            lookups.append(host)
            assert len(lookups) == 1, "must not re-resolve the original hostname after checking it"
            return actual_resolver("127.0.0.1", port, *args, **kwargs)
        return actual_resolver(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve_once)
    with local_peer(protocol, certificates, "matching" if case == "untrusted" else case,
                    connections=2 if case == "matching" else 1) as peer:
        pinned_ip = checked_connection_host(HOST, peer["port"])
        args = connect_args_for(protocol, "synthetic-password", pinned_ip=pinned_ip)
        driver = "postgresql+psycopg" if protocol == "postgresql" else "mysql+pymysql"
        engine = create_database_engine(f"{driver}://fixture@{HOST}:{peer['port']}/fixture", connect_args=args)
        # Only protocol handshakes, not SQLAlchemy's DB-engine capability queries.
        monkeypatch.setattr(engine.dialect, "initialize", lambda _connection: None)
        try:
            if case == "matching":
                for _ in range(2):
                    connection = engine.raw_connection()
                    connection.close()
                    engine.dispose()  # New pooled connections must retain pinning/identity.
            else:
                with pytest.raises((DBAPIError, psycopg.OperationalError, pymysql.err.OperationalError)) as caught:
                    engine.raw_connection()
                text = str(caught.value).lower()
                assert "certificate" in text or "hostname" in text
        finally:
            engine.dispose()
    assert len(lookups) == 1
    assert peer["connections"] == (2 if case == "matching" else 1)
    assert peer["credentials"] is (case == "matching")
    if case == "matching":
        assert peer["tls"] is True
        assert peer["sni"] == HOST


@pytest.mark.parametrize("protocol", ["smtps", "starttls"])
@pytest.mark.parametrize("case", ["matching", "wrong-host", "untrusted", "expired"])
def test_smtp_real_transport_checks_certificates_before_login(monkeypatch, certificates, protocol, case):
    ca = certificates / ("other-ca.pem" if case == "untrusted" else "ca.pem")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    actual_resolver = socket.getaddrinfo
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k:
                        actual_resolver("127.0.0.1" if host == HOST else host, port, *a, **k))
    with local_peer(protocol, certificates, "matching" if case == "untrusted" else case) as peer:
        for name, value in dict(smtp_server=HOST, smtp_port=peer["port"], smtp_username="fixture@example.test",
                                smtp_password="synthetic-password", smtp_from="fixture@example.test",
                                smtp_use_ssl=protocol == "smtps", smtp_use_tls=protocol == "starttls",
                                environment="production").items():
            monkeypatch.setattr(emailer.settings, name, value)
        if case == "matching":
            emailer.send_otp_email("recipient@example.test", "123456")
        else:
            with pytest.raises(emailer.EmailDeliveryError, match="delivery failed"):
                emailer.send_otp_email("recipient@example.test", "123456")
    assert peer["credentials"] is (case == "matching")
    if case == "matching":
        assert peer["tls"] is True
        assert peer["sni"] == HOST


def test_production_smtp_plaintext_refused_before_socket(monkeypatch):
    for name, value in dict(smtp_server=HOST, smtp_port=25, smtp_username="fixture@example.test",
                            smtp_password="synthetic-password", smtp_use_ssl=False, smtp_use_tls=False,
                            environment="production").items():
        monkeypatch.setattr(emailer.settings, name, value)
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("no plaintext socket"))
    with pytest.raises(emailer.EmailDeliveryError, match="TLS is required"):
        emailer.send_otp_email("recipient@example.test", "123456")


@pytest.mark.parametrize("factory", [_open_engine, ReadOnlyExecutor])
def test_both_schema_and_execution_install_pinned_mysql_transport(factory):
    args = connect_args_for("mysql", "synthetic-password", pinned_ip="8.8.8.8")
    result = factory("mysql+pymysql://fixture@tls-fixture.invalid/fixture", connect_args=args)
    engine = result.engine if isinstance(result, ReadOnlyExecutor) else result
    try:
        assert len(engine.dialect.dispatch.do_connect) == 1
        assert engine.url.host == HOST
    finally:
        engine.dispose()


@pytest.mark.parametrize("protocol", ["postgresql", "mysql"])
def test_database_refuses_tls_downgrade_before_auth(monkeypatch, certificates, protocol):
    monkeypatch.setenv("DB_SSL_REQUIRED", "true")
    monkeypatch.setenv("DB_SSL_CA", str(certificates / "ca.pem"))
    monkeypatch.setenv("DB_SSL_ROOT_CERT", str(certificates / "ca.pem"))
    with local_peer(protocol, certificates, supports_tls=False) as peer:
        args = connect_args_for(protocol, "synthetic-password", pinned_ip="127.0.0.1")
        driver = "postgresql+psycopg" if protocol == "postgresql" else "mysql+pymysql"
        engine = create_database_engine(f"{driver}://fixture@{HOST}:{peer['port']}/fixture", connect_args=args)
        try:
            with pytest.raises((DBAPIError, psycopg.OperationalError, pymysql.err.OperationalError)) as caught:
                engine.raw_connection()
            assert "ssl" in str(caught.value).lower()
        finally:
            engine.dispose()
    assert peer["credentials"] is False
    assert peer["tls"] is False


def test_starttls_not_advertised_does_not_fall_back_to_plaintext(monkeypatch, certificates):
    actual_resolver = socket.getaddrinfo
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k:
                        actual_resolver("127.0.0.1" if host == HOST else host, port, *a, **k))
    with local_peer("starttls", certificates, supports_tls=False) as peer:
        for name, value in dict(smtp_server=HOST, smtp_port=peer["port"], smtp_username="fixture@example.test",
                                smtp_password="synthetic-password", smtp_from="fixture@example.test",
                                smtp_use_ssl=False, smtp_use_tls=True, environment="production").items():
            monkeypatch.setattr(emailer.settings, name, value)
        with pytest.raises(emailer.EmailDeliveryError, match="delivery failed"):
            emailer.send_otp_email("recipient@example.test", "123456")
    assert peer["credentials"] is False
