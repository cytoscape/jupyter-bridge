# -*- coding: utf-8 -*-

""" Test functions in Jupyter-bridge.
"""

"""License:
    Copyright 2020 The Cytoscape Consortium

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
    documentation files (the "Software"), to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
    and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or substantial portions
    of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
    WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
    OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import unittest

from server.test_utils import *
import redis
import requests
import json

redis_db = redis.Redis('localhost')

TEST_JSON = {"command": "POST",
             "url": "http://somehost:9999/v1/commands/session/open",
             "params": None,
             "data": {"file": "C:\\Program Files\\Cytoscape_v3.9.0-SNAPSHOT-May 29\\sampleData\\galFiltered.cys"},
             "headers": {"Content-Type": "application/json", "Accept": "application/json"}
             }
BRIDGE_URL = 'http://localhost:5000'


class JupyterBridgeTests(unittest.TestCase):
    def setUp(self):
        # Get rid of all of test keys
        for key in redis_db.keys('test:*'):
            redis_db.delete(key)

    def tearDown(self):
        pass

    @print_entry_exit
    def test_ping(self):
        res = requests.get(f'{BRIDGE_URL}/ping', headers={'Content-Type': 'text/plain'})
        self.assertEqual(res.status_code, 200)
        self.assertRegex(res.text, 'pong +\d.+\d.+\d')

    @print_entry_exit
    def test_requests(self):
        self._test_basic_protocol('request', 'application/json')

        # Post a reply
        res = requests.post(f'{BRIDGE_URL}/queue_reply?channel=test', json=TEST_JSON,
                            headers={'Content-Type': 'text/plain'})
        self.assertEqual(res.status_code, 200)

        # Verify that when a reply is pending, a new request can't be posted
        res = requests.post(f'{BRIDGE_URL}/queue_request?channel=test', json=TEST_JSON,
                            headers={'Content-Type': 'application/json'})
        self.assertEqual(res.status_code, 500)

    @print_entry_exit
    def test_replies(self):
        self._test_basic_protocol('reply', 'text/plain')

    def _test_basic_protocol(self, operation, mime_type):
        # Verify that a timeout occurs when no operation is pending
        res = requests.get(f'{BRIDGE_URL}/dequeue_{operation}?channel=test')
        self.assertEqual(res.status_code, 408)

        # Verify that posting JSON succeeds
        res = requests.post(f'{BRIDGE_URL}/queue_{operation}?channel=test', json=TEST_JSON,
                            headers={'Content-Type': f'{mime_type}'})
        self.assertEqual(res.status_code, 200)

        # Verify that the posted JSON can be read back
        res = requests.get(f'{BRIDGE_URL}/dequeue_{operation}?channel=test')
        self.assertEqual(res.status_code, 200)
        message = json.loads(res.text)
        self.assertDictEqual(message, TEST_JSON)

        # Verify that a timeout occurs because no operation is pending
        res = requests.get(f'{BRIDGE_URL}/dequeue_{operation}?channel=test')
        self.assertEqual(res.status_code, 408)

        # Verify that posting JSON succeeds, but that a second post before a dequeue is rejected
        res = requests.post(f'{BRIDGE_URL}/queue_{operation}?channel=test', json=TEST_JSON,
                            headers={'Content-Type': f'{mime_type}'})
        self.assertEqual(res.status_code, 200)
        res = requests.post(f'{BRIDGE_URL}/queue_{operation}?channel=test', json=TEST_JSON,
                            headers={'Content-Type': f'{mime_type}'})
        self.assertEqual(res.status_code, 500)

        # Verify that the posted JSON can be read back
        res = requests.get(f'{BRIDGE_URL}/dequeue_{operation}?channel=test')
        self.assertEqual(res.status_code, 200)
        message = json.loads(res.text)
        self.assertDictEqual(message, TEST_JSON)

        # Verify that a timeout occurs because no operation is pending
        res = requests.get(f'{BRIDGE_URL}/dequeue_{operation}?channel=test')
        self.assertEqual(res.status_code, 408)


if __name__ == '__main__':
    unittest.main()
