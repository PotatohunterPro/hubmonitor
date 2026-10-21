from __future__ import annotations

import ssl

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

from server.tls import generate_local_certificate


def test_local_certificate_contains_ip_and_server_usage_and_loads_as_trust(tmp_path):
    cert_path, key_path, trust_path = generate_local_certificate(
        tmp_path, "bertolo-server.local", "192.168.0.110"
    )
    certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
    trust_anchor = x509.load_pem_x509_certificate(trust_path.read_bytes())
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    usage = certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value

    assert "192.168.0.110" in [str(value) for value in san.get_values_for_type(x509.IPAddress)]
    assert "bertolo-server.local" in san.get_values_for_type(x509.DNSName)
    assert ExtendedKeyUsageOID.SERVER_AUTH in usage
    assert certificate.issuer == trust_anchor.subject
    assert certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    assert trust_anchor.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    assert certificate.public_key().public_numbers() == private_key.public_key().public_numbers()
    assert ssl.create_default_context(cafile=str(trust_path)).verify_mode == ssl.CERT_REQUIRED
