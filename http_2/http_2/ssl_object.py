import ssl
from ssl import SSLContext

ALPN = ['h2', 'http/1.1', 'http/1']

class SSLConfig:

    def __init__(self,
                 ssl_handshake_timeout: int = 60,
                 ssl_shutdown_timeout: int = 60):

        self._ssl_handshake_timeout = ssl_handshake_timeout
        self._ssl_shutdown_timeout = ssl_shutdown_timeout
        self._ssl_context_store = SSLContextStore()
        self._default_ssl_context = None

    @property
    def ssl_handshake_timeout(self):
        return self._ssl_handshake_timeout

    @property
    def ssl_shutdown_timeout(self):
        return self._ssl_shutdown_timeout

    @property
    def default_ssl_context(self):
        if not self._default_ssl_context:
            raise RuntimeError('Unexpected circumstance, because there is no ssl context, but you configure '
                               '443 port.')
        return self._default_ssl_context

    def add_tls_with_hostname(self, hostname: str, certfile_path: str, keyfile_path: str) -> None:
        self._ssl_context_store.add_cert_chains(hostname, certfile_path, keyfile_path)

    def set_default_tls(self, certfile_path: str, keyfile_path: str) -> None:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.set_alpn_protocols(ALPN)
        ssl_context.load_cert_chain(certfile=certfile_path,
                                    keyfile=keyfile_path)
        self._default_ssl_context = ssl_context

    def sni_callback(self, ssl_sock, server_name, ssl_context):
        ctx = self._ssl_context_store.find_ssl_context_by_hostname(server_name)
        ssl_sock.context = ctx if ctx else ssl_context


class SSLContextStore:

    def __init__(self):
        self._store: dict[str, SSLContext | None] = {}

    def add_cert_chains(self,
                        hostname: str,
                        cert_file: str,
                        key_file: str) -> None:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.set_alpn_protocols(ALPN)
        ssl_context.load_cert_chain(certfile=cert_file,
                                    keyfile=key_file)
        self._store[hostname] = ssl_context

    def find_ssl_context_by_hostname(self, hostname: str) -> SSLContext:
        return self._store.get(hostname, None)
