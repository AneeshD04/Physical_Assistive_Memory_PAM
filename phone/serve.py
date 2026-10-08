"""Serves phone/index.html to the phone over HTTPS, and makes the certificate the relay also needs.

    python phone/serve.py                 # prints the https:// URL to open on the phone

Why HTTPS for a page on your own LAN: browsers only hand out the camera in a
"secure context". That means HTTPS, or an origin of localhost. The phone reaches
this laptop at something like 192.168.1.20, which is neither, so a plain
http:// page gets no camera on iOS Safari or Android Chrome — the request fails
with NotAllowedError and no prompt is ever shown.

So this script:
  1. Generates a self-signed certificate valid for this laptop's LAN IP
     (cert.pem / key.pem, gitignored) if one is not already there.
  2. Serves phone/index.html over HTTPS using it.

The same cert.pem / key.pem pair is what you pass to the relay:

    python memory_pipeline.py --source wss://0.0.0.0:8765 --cert phone/cert.pem --key phone/key.pem ...

Both must be HTTPS/WSS and both must use the SAME certificate, so the phone only
has to be told to trust one thing.

First connection from the phone, once per laptop:
  - Open the printed https:// URL. Safari warns the certificate is untrusted
    (expected: nobody signs a certificate for a private IP). Tap Show Details ->
    visit this website.
  - Then open https://<laptop-ip>:8765 once and accept the same warning, so the
    WebSocket to that port is allowed too. It will show an empty page or an
    error body; that is fine, the point is accepting the certificate.
"""
import argparse
import functools
import http.server
import ipaddress
import os
import socket
import time
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
CERT, KEY = HERE / "cert.pem", HERE / "key.pem"

if __package__ in (None, ""):
    sys.path.insert(0, str(HERE.parent))
from perception.private_files import private_append_fd

TLS_ROTATION = ("TLS pair is incomplete, invalid, expired or not valid for this IP. "
                "Refusing to overwrite it. Stop the service and manually archive both "
                "cert.pem and key.pem, then rerun to generate a new pair; explicitly "
                "approve the new certificate on your devices. No trust store was changed.")


class PublicFiles(http.server.SimpleHTTPRequestHandler):
    ASSET_SUFFIXES = {".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".txt"}

    def send_head(self):
        try:
            url = urlsplit(self.path)
            decoded = unquote(url.path)
            if url.scheme or url.netloc or any(ord(char) < 32 or ord(char) == 127 for char in decoded):
                raise ValueError("Invalid public path")
            if any(part.startswith(".") or "\\" in part or ":" in part for part in decoded.split("/")):
                raise ValueError("Invalid public path")
            root = Path(self.directory).resolve()
            path = Path(self.translate_path(self.path)).resolve()
            if path == root:
                path = (root / "index.html").resolve()
            relative = path.relative_to(root)
            page = relative.as_posix() in {"index.html", "agent.html", "memory.html"}
            # assets/models/ (pinned model files and their manifest) is served only by
            # the combined app, whose route is gated on the manifest, the licence
            # register and PAM_ENABLE_HAND_MODEL; this suffix allowlist never is.
            asset = (len(relative.parts) > 1 and relative.parts[0] == "assets"
                     and relative.parts[1] != "models"
                     and path.suffix.lower() in self.ASSET_SUFFIXES
                     and not any(part.startswith(".") or ":" in part for part in relative.parts))
            if not (page or asset) or not path.is_file():
                raise ValueError("Not a public file")
        except (OSError, ValueError, RuntimeError):
            self.send_error(404, "File not found")
            return None
        return super().send_head()

    def list_directory(self, path):
        self.send_error(404, "File not found")
        return None


def lan_ip() -> str:
    """This laptop's address on the local network, as the phone will reach it.

    Opens a UDP socket toward a public address and reads back which local
    interface the OS picked. No packet is actually sent, and it does not need
    the internet to work — it only asks the routing table a question.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert(ip: str) -> None:
    """Create a self-signed cert covering this IP, unless one already exists.

    The IP goes in a subjectAltName, not just the common name: browsers have
    ignored the common name for host matching for years and will reject a cert
    without a matching SAN even after you accept the warning.
    """
    if not isinstance(ip, str) or len(ip) > 45 or "%" in ip:
        raise ValueError("A bounded numeric IPv4 or IPv6 address is required.")
    try:
        ip = str(ipaddress.ip_address(ip))
    except ValueError:
        raise ValueError("A numeric IPv4 or IPv6 address is required.") from None
    if CERT.is_symlink() or KEY.is_symlink():
        raise FileExistsError(TLS_ROTATION)

    def protect_key():
        # Applies owner-only POSIX mode / protected Windows DACL before key bytes.
        fd = private_append_fd(KEY)
        os.close(fd)

    def validate_pair():
        try:
            decoded = ssl._ssl._test_decode_cert(str(CERT))
            sans = decoded.get("subjectAltName", ())
            ips = {ipaddress.ip_address(value) for kind, value in sans if kind == "IP Address"}
            if ipaddress.ip_address(ip) not in ips or ipaddress.ip_address("127.0.0.1") not in ips:
                raise ValueError("SAN mismatch")
            if ("DNS", "localhost") not in sans:
                raise ValueError("Missing localhost SAN")
            if not (ssl.cert_time_to_seconds(decoded["notBefore"]) <= time.time()
                    < ssl.cert_time_to_seconds(decoded["notAfter"])):
                raise ValueError("Invalid validity period")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(CERT, KEY)
        except Exception:
            raise FileExistsError(TLS_ROTATION) from None

    if CERT.exists() and KEY.exists():
        protect_key()
        validate_pair()
        return
    if CERT.exists() or KEY.exists():
        raise FileExistsError(TLS_ROTATION)
    # Reserve both names exclusively; no pre-existing file can be overwritten.
    # On any failure leave the partial pair for explicit manual inspection/rotation.
    for path in (KEY, CERT):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except OSError:
            raise FileExistsError(TLS_ROTATION) from None
    protect_key()
    print(f"generating a self-signed certificate for {ip} ...")
    try:
        subprocess.run(
            ["openssl", "req", "-config", "-", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
             "-keyout", str(KEY), "-out", str(CERT), "-days", "365",
             "-subj", "/CN=compass-laptop",
             "-addext", f"subjectAltName=IP:{ip},IP:127.0.0.1,DNS:localhost",
             "-addext", "basicConstraints=critical,CA:FALSE",
             "-addext", "keyUsage=critical,digitalSignature,keyEncipherment",
             "-addext", "extendedKeyUsage=serverAuth"],
            check=True, capture_output=True, text=True, timeout=30,
            input="[req]\ndistinguished_name=dn\nprompt=no\n[dn]\nCN=compass-laptop\n",
        )
    except (subprocess.SubprocessError, OSError):
        # Never stringify provider output: OpenSSL errors can contain private material.
        raise RuntimeError("Certificate generation failed. " + TLS_ROTATION) from None
    protect_key()
    validate_pair()
    print(f"wrote {CERT.name} and {KEY.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--relay-port", type=int, default=8765, help="only used for the printed instructions")
    args = ap.parse_args()

    ip = lan_ip()
    try:
        ensure_cert(ip)
    except FileExistsError as e:
        sys.exit(str(e))
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError):
        sys.exit("Could not prepare a private TLS certificate. " + TLS_ROTATION)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)

    # Serve only this directory, whatever the shell's working directory is.
    handler = functools.partial(PublicFiles, directory=str(HERE))
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print(f"\n  On the phone, open:  https://{ip}:{args.port}/")
    print(f"  Accept the certificate warning, then also visit https://{ip}:{args.relay_port} once")
    print(f"  and accept it there, so the WebSocket to the relay is allowed.\n")
    print("  Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
