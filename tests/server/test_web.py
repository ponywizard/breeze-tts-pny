"""Web listener addressing, CLI wiring and authentication without model weights."""
import http.client
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
from breeze_pny.__main__ import main
from breeze_pny.web import browser_hosts, create_server


class WebChecks(unittest.TestCase):
    def start(self, host='127.0.0.1'):
        companion = Mock()
        companion.state.return_value = {'ready': True}
        companion.stopping.is_set.return_value = False
        companion.submit.return_value = {'accepted': True}
        server, token = create_server(companion, 0, host)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def close():
            server.shutdown(); server.server_close(); thread.join()
        self.addCleanup(close)
        return companion, server, token

    def call(self, server, token, address='127.0.0.1', host=None, origin=None, method='GET', extra=()):
        connection = http.client.HTTPConnection(address, server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest(method, '/api/models' if method == 'POST' else '/api/state', skip_host=True)
        connection.putheader('Host', host if host is not None else f'{address}:{server.server_port}')
        connection.putheader('X-Breeze-Token', token)
        if origin is not None: connection.putheader('Origin', origin)
        for key, value in extra: connection.putheader(key, value)
        body = b'{"action":"unload"}' if method == 'POST' else b''
        connection.putheader('Content-Type', 'application/json')
        connection.putheader('Content-Length', str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse(); response.read()
        return response.status

    def test_default_and_specific_listener_addresses(self):
        for host in ('127.0.0.1', '127.0.0.2'):
            with self.subTest(host=host):
                _, server, token = self.start(host)
                self.assertEqual(server.server_address[0], host)
                self.assertEqual(self.call(server, token, address=host), 200)
                self.assertEqual(self.call(server, token, address=host, origin=f'http://{host}:{server.server_port}', method='POST'), 202)

    def test_wildcard_uses_actual_destination_and_keeps_authentication(self):
        companion, server, token = self.start('0.0.0.0')
        self.assertEqual(server.server_address[0], '0.0.0.0')
        for address in ('127.0.0.1', '127.0.0.2'):
            origin = f'http://{address}:{server.server_port}'
            self.assertEqual(self.call(server, token, address=address, origin=origin), 200)
            self.assertEqual(self.call(server, token, address=address, origin=origin, method='POST'), 202)
        companion.submit.reset_mock()
        for host, origin, auth in (
                (f'localhost:{server.server_port}', None, token),
                (f'0.0.0.0:{server.server_port}', None, token),
                (f'127.0.0.2:{server.server_port}', None, token),
                ('attacker.invalid', 'http://attacker.invalid', token),
                (None, 'http://attacker.invalid', token),
                (None, f'http://127.0.0.2:{server.server_port}', token),
                (None, 'null', token), (None, None, ''), (None, None, 'wrong')):
            for method in ('GET', 'POST'):
                with self.subTest(host=host, origin=origin, token=auth, method=method):
                    self.assertEqual(self.call(server, auth, host=host, origin=origin, method=method), 403)
        for extra in ((('Host', 'attacker.invalid'),), (('Origin', 'http://attacker.invalid'),)):
            self.assertEqual(self.call(server, token, origin=f'http://127.0.0.1:{server.server_port}', extra=extra), 403)
        companion.submit.assert_not_called()

    def test_invalid_bind_addresses_are_rejected(self):
        for host in ('localhost', '::1', '192.168.1.999', 'https://192.168.1.2'):
            with self.subTest(host=host), self.assertRaises(ValueError): create_server(Mock(), 0, host)

    def test_browser_links_and_discovery_failure(self):
        self.assertEqual(browser_hosts('192.168.1.25'), ['192.168.1.25'])
        addresses = ['192.168.1.25', '192.168.1.25', '127.0.1.1', '0.0.0.0', '224.0.0.1']
        with patch('breeze_pny.web.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (a, 0)) for a in addresses]):
            self.assertEqual(browser_hosts('0.0.0.0'), ['127.0.0.1', '192.168.1.25'])
        with patch('breeze_pny.web.socket.getaddrinfo', side_effect=OSError):
            self.assertEqual(browser_hosts('0.0.0.0'), ['127.0.0.1'])

    def test_cli_passes_web_and_api_hosts_independently(self):
        args = ['breeze-pny', 'serve', '--web', '--config', 'config.json', '--no-browser']
        for extra, web_host, api_host in (([], '127.0.0.1', None),
                                        (['--web-host', '0.0.0.0'], '0.0.0.0', None),
                                        (['--host', '0.0.0.0', '--web-host', '192.168.1.25'], '192.168.1.25', '0.0.0.0')):
            with self.subTest(extra=extra), patch.object(sys, 'argv', args + extra), patch('breeze_pny.web.run') as run:
                self.assertEqual(main(), 0)
                self.assertEqual(run.call_args.kwargs['web_host'], web_host)
                self.assertEqual(run.call_args.args[1], api_host)
                self.assertFalse(run.call_args.args[5])


if __name__ == '__main__': unittest.main()
