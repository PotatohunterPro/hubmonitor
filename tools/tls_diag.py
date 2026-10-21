import socket, ssl, subprocess, sys

HOST = "nfce.fazenda.sp.gov.br"

candidates = []
try:
    import certifi
    candidates.append(("certifi", certifi.where()))
except Exception as exc:
    print("certifi indisponivel:", exc)
candidates.append(("macOS /private/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"))

for label, cafile in candidates:
    try:
        ctx = ssl.create_default_context(cafile=cafile)
        with socket.create_connection((HOST, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=HOST) as tls:
                cert = tls.getpeercert()
                print(f"[OK  ] {label}: {tls.version()}")
                print(f"        subject={dict(x[0] for x in cert['subject']).get('commonName')}")
                print(f"        issuer ={dict(x[0] for x in cert['issuer']).get('commonName')}")
    except Exception as exc:
        print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")

print()
print("--- raizes ICP-Brasil presentes nos bundles ---")
for label, cafile in candidates:
    try:
        with open(cafile, "r", errors="replace") as handle:
            text = handle.read()
        hits = [line for line in text.splitlines() if "ICP-Brasil" in line or "Brasileira" in line]
        print(f"{label}: {len(hits)} ocorrencias")
        for line in hits[:5]:
            print("   ", line.strip())
    except OSError as exc:
        print(f"{label}: erro {exc}")

print()
print("--- keychain de raizes do macOS ---")
out = subprocess.run(
    ["security", "find-certificate", "-a", "-c", "Brasileira", "-Z", "/System/Library/Keychains/SystemRootCertificates.keychain"],
    capture_output=True, text=True,
)
print((out.stdout or out.stderr).strip()[:800] or "nenhuma")
