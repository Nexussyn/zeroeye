"""Regression tests for log aggregator parsers.

These tests use independently curated sample log lines to validate
parser behavior against real-world examples.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

try:
    from log_aggregator import parse_json_log, parse_plain_log, parse_nginx_log
except ImportError:
    parse_json_log = parse_plain_log = parse_nginx_log = None


class TestJsonLogParser(unittest.TestCase):
    """Tests for JSON log parsing."""

    def setUp(self):
        if parse_json_log is None:
            self.skipTest("log_aggregator not available")

    def test_valid_json_with_all_fields(self):
        line = '{"timestamp":"2024-01-15T10:30:00Z","level":"INFO","msg":"Started"}'
        result = parse_json_log(line)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("level"), "INFO")

    def test_malformed_json_missing_brace(self):
        line = '{"timestamp":"2024-01-15T10:30:00Z","level":"ERROR"'
        result = parse_json_log(line)
        self.assertIsNone(result)

    def test_empty_json_object(self):
        line = '{}'
        result = parse_json_log(line)
        self.assertIsNotNone(result)


class TestPlainLogParser(unittest.TestCase):
    """Tests for plain text log parsing."""

    def setUp(self):
        if parse_plain_log is None:
            self.skipTest("log_aggregator not available")

    def test_standard_format(self):
        line = "2024-01-15 10:30:00 INFO Application started"
        result = parse_plain_log(line)
        self.assertIsNotNone(result)

    def test_empty_line(self):
        result = parse_plain_log("")
        self.assertIsNone(result)


class TestNginxLogParser(unittest.TestCase):
    """Tests for Nginx access log parsing."""

    def setUp(self):
        if parse_nginx_log is None:
            self.skipTest("log_aggregator not available")

    def test_combined_format(self):
        line = '192.168.1.1 - - [15/Jan/2024:10:30:00 +0000] "GET /api/v1/health HTTP/1.1" 200 15 "-" "curl/7.68.0"'
        result = parse_nginx_log(line)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("status"), "200")

    def test_malformed_nginx_line(self):
        line = "not a valid nginx log line"
        result = parse_nginx_log(line)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
