# Fix for Issue #5: [ BOUNTY] [Python] Fix false pass rate in log parser test suite

# tools/log_aggregator.py
import re

class LogAggregator:
    def __init__(self, log_file):
        self.log_file = log_file

    def parse_log(self):
        pattern = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\w+) (\d+) (\w+) (.*)$"
        logs = []
        with open(self.log_file, 'r') as f:
            for line in f:
                match = re.match(pattern, line)
                if match:
                    log = {
                        'timestamp': match.group(1),
                        'level': match.group(2),
                        'pid': match.group(3),
                        'module': match.group(4),
                        'message': match.group(5)
                    }
                    logs.append(log)
        return logs