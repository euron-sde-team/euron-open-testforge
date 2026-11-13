# A probe that runs inside the sandbox only (never collected here: its file name is not test_*).
# Runs inside the sandbox. Every test that reaches out must FAIL: a run has no network.
import socket
import urllib.request


def test_tcp_to_the_internet():
    socket.create_connection(("1.1.1.1", 53), timeout=3).close()


def test_dns_lookup():
    socket.getaddrinfo("example.com", 443)


def test_http_request():
    urllib.request.urlopen("http://93.184.215.14/", timeout=3).read()


def test_platform_services():
    # The API, Postgres and Redis on the Compose network, by name and by private address.
    for host, port in (("api", 8080), ("postgres", 5432), ("redis", 6379), ("10.0.0.1", 5432)):
        socket.create_connection((host, port), timeout=2).close()


def test_cloud_metadata_service():
    socket.create_connection(("169.254.169.254", 80), timeout=3).close()


def test_only_loopback_is_up():
    # This one passes: the run's own network namespace has no interface up but loopback.
    # (The kernel adds its fallback tunnel devices, tunl0 and gre0, to every namespace;
    # they are down and have no address.)
    import fcntl
    import struct

    up = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for _, name in socket.if_nameindex():
            req = struct.pack("16sH14s", name.encode(), 0, b"")
            flags = struct.unpack("16sH14s", fcntl.ioctl(s.fileno(), 0x8913, req))[1]
            if flags & 0x1:
                up.append(name)
    assert set(up) <= {"lo"}, up
