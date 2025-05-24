import socket
import ssl
import random
import threading
import time
from typing import Optional

# User agents list for request headers
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:114.0) Gecko/20100101 Firefox/114.0",
]

def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)

def raw_http_request(
    host: str,
    port: int = 80,
    use_ssl: bool = False,
    method: str = "GET",
    path: str = "/",
    headers: Optional[dict] = None,
    body: Optional[str] = None,
    timeout: int = 5,
) -> str:
    if headers is None:
        headers = {}

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        if use_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        req_lines = [f"{method} {path} HTTP/1.1",
                     f"Host: {host}",
                     f"User-Agent: {get_random_user_agent()}"]

        for k, v in headers.items():
            req_lines.append(f"{k}: {v}")

        if body:
            req_lines.append(f"Content-Length: {len(body)}")

        req_lines.append("Connection: close")
        req_lines.append("")  # blank line to end headers

        if body:
            req_lines.append(body)

        request_data = "\r\n".join(req_lines).encode()

        sock.sendall(request_data)

        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
        sock.close()

        return response.decode(errors="ignore")

    except Exception as e:
        return f"Error: {e}"

def worker_thread(host: str, port: int, use_ssl: bool, path: str, duration: int):
    end_time = time.time() + duration
    while time.time() < end_time:
        response = raw_http_request(host, port, use_ssl, path=path)
        # Optional: print minimal info per request or just pass
        # print(f"Requested {host}{path} - Response size: {len(response)}")
        time.sleep(0.1)  # short delay between requests

def run_load_test(host: str, port: int, use_ssl: bool, path: str, duration: int, threads_count: int):
    threads = []
    print(f"Starting load test on {host}:{port}{path} for {duration}s with {threads_count} threads...")

    for _ in range(threads_count):
        t = threading.Thread(target=worker_thread, args=(host, port, use_ssl, path, duration))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    print("Load test completed.")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Advanced HTTP load tester")
    parser.add_argument("host", help="Target host or IP")
    parser.add_argument("--port", type=int, default=80, help="Target port (default 80)")
    parser.add_argument("--https", action="store_true", help="Use HTTPS (default HTTP)")
    parser.add_argument("--path", default="/", help="Request path (default /)")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in seconds (default 30)")
    parser.add_argument("--threads", type=int, default=10, help="Number of concurrent threads (default 10)")

    args = parser.parse_args()

    run_load_test(args.host, args.port, args.https, args.path, args.duration, args.threads)

if __name__ == "__main__":
    main()
