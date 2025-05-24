import socket
import ssl
import random
import threading
import time
import sys
from queue import Queue

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:114.0) Gecko/20100101 Firefox/114.0",
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def raw_http_request(host, port=80, use_ssl=False, method="GET", path="/", headers=None, timeout=5):
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

        req_lines.append("Connection: close")
        req_lines.append("")  # End headers

        request_data = "\r\n".join(req_lines).encode()

        sock.sendall(request_data)

        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
        sock.close()
        return response.decode(errors='ignore')
    except Exception as e:
        return f"Error: {e}"

class LoadTester:
    def __init__(self, host, port=80, use_ssl=False, path="/", concurrency=10, total_requests=100, interval=0):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.path = path
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.interval = interval

        self.queue = Queue()
        self.lock = threading.Lock()
        self.success = 0
        self.errors = 0

    def worker(self):
        while True:
            if self.queue.empty():
                break
            try:
                _ = self.queue.get_nowait()
            except:
                break

            response = raw_http_request(self.host, self.port, self.use_ssl, path=self.path)

            with self.lock:
                if response.startswith("Error:"):
                    self.errors += 1
                else:
                    self.success += 1

            self.queue.task_done()
            if self.interval > 0:
                time.sleep(self.interval)

    def run(self):
        print(f"Starting load test on {self.host}:{self.port}{self.path} with concurrency={self.concurrency}, total requests={self.total_requests}")
        for _ in range(self.total_requests):
            self.queue.put(1)

        threads = []
        for _ in range(self.concurrency):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()
            threads.append(t)

        self.queue.join()
        print("Load test complete.")
        print(f"Successful requests: {self.success}")
        print(f"Failed requests: {self.errors}")

def print_help():
    print("""
Usage:
python main.py <host> [port] [https] [path] [concurrency] [total_requests] [interval]

Parameters:
 host           - Target hostname or IP (required)
 port           - Target port (default: 80)
 https          - Use HTTPS? 1=yes, 0=no (default: 0)
 path           - HTTP path (default: /)
 concurrency    - Number of concurrent threads (default: 10)
 total_requests - Total number of requests (default: 100)
 interval       - Interval between requests in seconds (default: 0)
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    use_ssl = bool(int(sys.argv[3])) if len(sys.argv) > 3 else False
    path = sys.argv[4] if len(sys.argv) > 4 else "/"
    concurrency = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    total_requests = int(sys.argv[6]) if len(sys.argv) > 6 else 100
    interval = float(sys.argv[7]) if len(sys.argv) > 7 else 0

    tester = LoadTester(host, port, use_ssl, path, concurrency, total_requests, interval)
    tester.run()
