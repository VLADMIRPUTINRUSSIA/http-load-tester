#!/usr/bin/env python3

import socket
import ssl
import threading
import time
import random
import platform
import json
import sys
from queue import Queue

from fpdf import FPDF
from scapy.all import IP, TCP, sr1
from prometheus_client import start_http_server, Counter
import paho.mqtt.client as mqtt

# ---------- Configuration ---------- #
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:114.0)...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_5)...",
    "Mozilla/5.0 (Windows NT 6.1; WOW64)...",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F)...",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "curl/7.79.1"
]

# Prometheus Metrics
requests_total = Counter('loadtest_requests_total', 'Total Requests Sent')
requests_failed = Counter('loadtest_requests_failed', 'Failed Requests')

# ---------- Utilities ---------- #
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def resolve_hostname(host):
    try:
        ip = socket.gethostbyname(host)
        print(f"[nslookup] {host} resolved to {ip}")
        return ip
    except socket.gaierror as e:
        print(f"[nslookup error] Could not resolve {host}: {e}")
        return None

def generate_pdf_report(success_count, fail_count, elapsed):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Load Test Report", ln=1, align='C')
    pdf.cell(200, 10, txt=f"Success: {success_count}", ln=2)
    pdf.cell(200, 10, txt=f"Failures: {fail_count}", ln=3)
    pdf.cell(200, 10, txt=f"Elapsed Time: {elapsed:.2f}s", ln=4)
    pdf.output("report.pdf")

# ---------- Raw Request Core ---------- #
def raw_http_request(host, port=80, use_ssl=False, method="GET", path="/", headers=None, timeout=5, verbose=False):
    if headers is None:
        headers = {}

    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        if use_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)

        request_lines = [f"{method} {path} HTTP/1.1",
                         f"Host: {host}",
                         f"User-Agent: {get_random_user_agent()}"]

        for k, v in headers.items():
            request_lines.append(f"{k}: {v}")

        request_lines.append("Connection: close")
        request_lines.append("")

        request_data = "\r\n".join(request_lines).encode()
        sock.sendall(request_data)

        if verbose:
            print("[Request Headers]", "\n".join(request_lines))

        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk

        sock.close()
        return response.decode(errors='ignore')

    except Exception as e:
        return f"Error: {e}"

# ---------- Load Tester Class ---------- #
class LoadTester:
    def __init__(self, host, port=80, use_ssl=False, path="/", concurrency=10, total_requests=100, interval=0, verbose=False):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.path = path
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.interval = interval
        self.verbose = verbose

        self.queue = Queue()
        self.lock = threading.Lock()
        self.success = 0
        self.errors = 0
        self.responses = []

    def worker(self):
        while not self.queue.empty():
            try:
                _ = self.queue.get_nowait()
                response = raw_http_request(self.host, self.port, self.use_ssl, path=self.path, verbose=self.verbose)
                with self.lock:
                    if response.startswith("Error:"):
                        self.errors += 1
                        requests_failed.inc()
                    else:
                        self.success += 1
                        requests_total.inc()
                        self.responses.append(response[:200])
            except Exception:
                with self.lock:
                    self.errors += 1
                    requests_failed.inc()
            finally:
                self.queue.task_done()
                if self.interval > 0:
                    time.sleep(self.interval)

    def run(self):
        print(f"\n[+] Starting Load Test on {self.host}:{self.port}{self.path}")
        resolved_ip = resolve_hostname(self.host)
        if not resolved_ip:
            return

        for _ in range(self.total_requests):
            self.queue.put(1)

        threads = []
        start_time = time.time()

        for _ in range(self.concurrency):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()
            threads.append(t)

        self.queue.join()
        elapsed = time.time() - start_time

        print(f"\n[✓] Load Test Complete in {elapsed:.2f}s")
        print(f"Success: {self.success}, Errors: {self.errors}")
        if self.verbose and self.responses:
            for i, r in enumerate(self.responses[:3]):
                print(f"\n[{i+1}]:\n{r}\n")

        generate_pdf_report(self.success, self.errors, elapsed)

# ---------- OS Fingerprint ---------- #
def fingerprint_tcp_stack(target_ip):
    pkt = IP(dst=target_ip)/TCP(dport=80, flags="S")
    resp = sr1(pkt, timeout=2, verbose=0)
    if resp:
        print(f"[TCP-FP] TTL={resp.ttl}, Window={resp[TCP].window}, Options={resp[TCP].options}")

# ---------- MQTT Worker Listener ---------- #
def mqtt_on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    if payload.get('task') == 'loadtest':
        t = LoadTester(**payload['params'])
        t.run()

def start_mqtt_worker():
    client = mqtt.Client("advanced_worker")
    client.on_message = mqtt_on_message
    client.connect("broker.hivemq.com")
    client.subscribe("advanced/loadtest")
    client.loop_forever()

# ---------- Main CLI ---------- #
def print_help():
    print("""
Usage:
 python3 main.py <host> [port] [https] [path] [concurrency] [total_requests] [interval] [verbose]

Example:
 python3 main.py example.com 443 1 /test 10 100 0 1
    """)

if __name__ == "__main__":
    start_http_server(8000)  # Prometheus metrics server

    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    use_ssl = bool(int(sys.argv[3])) if len(sys.argv) > 3 else False
    if use_ssl and port == 80:
        port = 443
    path = sys.argv[4] if len(sys.argv) > 4 else "/"
    concurrency = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    total_requests = int(sys.argv[6]) if len(sys.argv) > 6 else 100
    interval = float(sys.argv[7]) if len(sys.argv) > 7 else 0
    verbose = bool(int(sys.argv[8])) if len(sys.argv) > 8 else False

    tester = LoadTester(host, port, use_ssl, path, concurrency, total_requests, interval, verbose)
    tester.run()

    # Optional: Uncomment for TCP fingerprinting
    # fingerprint_tcp_stack(resolve_hostname(host))
