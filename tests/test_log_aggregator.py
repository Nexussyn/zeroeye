# Fix for Issue #5: [ BOUNTY] [Python] Fix false pass rate in log parser test suite

# tests/test_log_aggregator.py
import unittest
from tools.log_aggregator import LogAggregator
import os

class TestLogAggregator(unittest.TestCase):
    def setUp(self):
        self.log_file = 'tests/fixtures/sample.log'
        self.log_aggregator = LogAggregator(self.log_file)

    def test_parse_log(self):
        logs = self.log_aggregator.parse_log()
        self.assertEqual(len(logs), 10)  # assuming 10 logs in the sample file

    def test_log_fields(self):
        logs = self.log_aggregator.parse_log()
        for log in logs:
            self.assertIn('timestamp', log)
            self.assertIn('level', log)
            self.assertIn('pid', log)
            self.assertIn('module', log)
            self.assertIn('message', log)

    def test_edge_cases(self):
        # test malformed line
        with open(self.log_file, 'a') as f:
            f.write('malformed line\n')
        logs = self.log_aggregator.parse_log()
        self.assertEqual(len(logs), 10)  # the malformed line should be ignored

        # test empty file
        with open(self.log_file, 'w') as f:
            f.write('')
        logs = self.log_aggregator.parse_log()
        self.assertEqual(len(logs), 0)

        # test non-existent file
        non_existent_file = 'tests/fixtures/non_existent.log'
        log_aggregator = LogAggregator(non_existent_file)
        with self.assertRaises(FileNotFoundError):
            log_aggregator.parse_log()

if __name__ == '__main__':
    unittest.main()