"""Real loopback regression for browser preconnections stalling the local UI."""
import json
import socket
import threading
import unittest
from contextlib import ExitStack
from http.client import HTTPConnection
from wsgiref.simple_server import make_server

from finbot.demo import DemoApp, DemoRequestHandler, DemoServer


class DemoServerConnections(unittest.TestCase):
    def test_idle_and_incomplete_connections_do_not_block_the_study(self):
        accepted = threading.Event()

        class TrackingServer(DemoServer):
            def process_request(self, request, client_address):
                accepted.set()
                super().process_request(request, client_address)

        with make_server("127.0.0.1", 0, DemoApp(), server_class=TrackingServer,
                         handler_class=DemoRequestHandler) as server:
            server.set_app(DemoApp(server.server_port))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with ExitStack() as clients:
                    address = ("127.0.0.1", server.server_port)
                    clients.enter_context(socket.create_connection(address, timeout=2))
                    self.assertTrue(accepted.wait(2), "Idle connection was not accepted")
                    accepted.clear()
                    partial = clients.enter_context(socket.create_connection(address, timeout=2))
                    partial.sendall((f"POST /api/study HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                                     "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{").encode())
                    self.assertTrue(accepted.wait(2), "Incomplete request was not accepted")
                    client = HTTPConnection(*address, timeout=2)
                    clients.callback(client.close)
                    client.request("GET", "/study")
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"Find the payment you mean", response.read())
                    client.request("GET", "/api/study")
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read())["protocol"], "finbot-structured-pilot-v1")
            finally:
                server.shutdown()
                worker.join(timeout=3)
                self.assertFalse(worker.is_alive())

    def test_unused_connection_is_closed_after_timeout(self):
        class ShortTimeoutHandler(DemoRequestHandler):
            timeout = .05

        with make_server("127.0.0.1", 0, DemoApp(), server_class=DemoServer,
                         handler_class=ShortTimeoutHandler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with socket.create_connection(("127.0.0.1", server.server_port), timeout=2) as idle:
                    self.assertEqual(idle.recv(1), b"")
            finally:
                server.shutdown()
                worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
