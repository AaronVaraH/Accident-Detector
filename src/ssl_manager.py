"""
Gestor de Certificados SSL/TLS y Validación de Ruta Segura HTTPS para Cámara.
Garantiza:
1. Generación automática de certificados X.509 autofirmados con Subject Alternative Names (SAN)
   para `localhost`, `127.0.0.1` y la IP LAN actual del servidor cuando se ejecuta en red local.
2. Detección transparente de HTTPS nativo o detrás de Reverse Proxy en la nube (Render / Cloudflare).
3. Diagnóstico de ruta segura para habilitar `navigator.mediaDevices.getUserMedia` en dispositivos móviles.
"""

import datetime
import ipaddress
import logging
import socket
from pathlib import Path
from typing import Any, Dict, Tuple

from config import settings

logger = logging.getLogger("SSLManager")


def get_local_lan_ip() -> str:
    """Detecta la dirección IP local de la máquina en la red Wi-Fi / LAN."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_ssl_certificates(
    cert_path: Path = settings.SSL_CERT_PATH,
    key_path: Path = settings.SSL_KEY_PATH,
    force_regenerate: bool = False,
) -> Tuple[Path, Path]:
    """
    Verifica que existan certificados SSL válidos en `config/certs/`.
    Si no existen o se solicita regeneración, crea un par X.509 RSA 2048-bit con SANs
    incluyendo `localhost`, `127.0.0.1` y la IP LAN actual.
    """
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    local_ip = get_local_lan_ip()

    if cert_path.exists() and key_path.exists() and not force_regenerate:
        try:
            from cryptography import x509
            cert_bytes = cert_path.read_bytes()
            cert_obj = x509.load_pem_x509_certificate(cert_bytes)
            san_ext = cert_obj.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            ips_in_cert = [str(ip) for ip in san_ext.value.get_values_for_type(x509.IPAddress)]
            if local_ip in ips_in_cert or local_ip == "127.0.0.1":
                return cert_path, key_path
            logger.info(f"Regenerando certificado SSL para incluir la IP LAN actual ({local_ip})...")
        except Exception:
            pass

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "MX"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CDMX"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Ciudad de Mexico"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TITAN Vision Tactical Security"),
            x509.NameAttribute(NameOID.COMMON_NAME, local_ip),
        ])

        san_entries = [
            x509.DNSName("localhost"),
            x509.DNSName("*.onrender.com"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
        if local_ip and local_ip != "127.0.0.1":
            try:
                san_entries.append(x509.IPAddress(ipaddress.ip_address(local_ip)))
            except ValueError:
                pass

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now_utc - datetime.timedelta(days=1))
            .not_valid_after(now_utc + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(private_key, hashes.SHA256())
        )

        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        logger.info(f"Certificados SSL generados para HTTPS en {cert_path} (IP: {local_ip})")
    except Exception as e:
        logger.warning(f"No se pudo autogenerar certificado SSL con cryptography: {e}")

    return cert_path, key_path


def evaluate_request_security(request_scheme: str, headers: Dict[str, str], host: str) -> Dict[str, Any]:
    """
    Evalúa si una petición entrante utiliza una ruta segura HTTPS (directa o vía proxy TLS como Render)
    para autorizar la transmisión de cámara (`getUserMedia` + `wss://`).
    """
    forwarded_proto = headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    effective_scheme = forwarded_proto or request_scheme.lower()
    is_https = effective_scheme == "https"

    hostname = host.split(":")[0].strip().lower()
    is_localhost = hostname in ("localhost", "127.0.0.1", "::1")

    # Para la cámara: HTTPS es obligatorio en red/producción; localhost sólo es válido en pruebas locales de escritorio
    camera_route_valid = is_https or is_localhost
    ws_scheme = "wss" if is_https else "ws"

    local_ip = get_local_lan_ip()
    port_part = f":{host.split(':')[1]}" if ":" in host else ""
    https_target_host = f"{local_ip}{port_part}" if is_localhost and local_ip != "127.0.0.1" else host

    return {
        "is_https": is_https,
        "is_localhost": is_localhost,
        "effective_scheme": effective_scheme,
        "camera_secure_context_valid": camera_route_valid,
        "strict_https_verified": is_https,
        "websocket_uplink_url": f"{ws_scheme}://{host}/ws/uplink",
        "websocket_telemetry_url": f"{ws_scheme}://{host}/ws/telemetry",
        "recommended_https_url": f"https://{https_target_host}",
        "lan_https_url": f"https://{local_ip}{port_part}",
        "environment": settings.ENVIRONMENT,
        "force_https_enabled": settings.FORCE_HTTPS,
    }

