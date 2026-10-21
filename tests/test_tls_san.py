"""Certificado do servidor: o loopback precisa estar nos SANs."""

from __future__ import annotations

from cryptography import x509

from server.tls import generate_local_certificate


def test_certificado_inclui_loopback_para_o_agente_local(tmp_path):
    cert, _key, _ca = generate_local_certificate(tmp_path, "SERVIDOR-TESTE", "192.168.0.110")

    dados = x509.load_pem_x509_certificate(cert.read_bytes())
    san = dados.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    valores = {str(item.value) for item in san}

    assert "192.168.0.110" in valores
    assert "127.0.0.1" in valores
    assert "localhost" in valores
    assert "SERVIDOR-TESTE" in valores


def test_certificado_nao_duplica_san_quando_o_ip_e_o_loopback(tmp_path):
    cert, _key, _ca = generate_local_certificate(tmp_path, "127.0.0.1", "127.0.0.1")

    dados = x509.load_pem_x509_certificate(cert.read_bytes())
    san = dados.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    assert len([item for item in san if str(item.value) == "127.0.0.1"]) == 1
