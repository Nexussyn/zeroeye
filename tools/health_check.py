# Fix for Issue #2: [$50 BOUNTY] [Python] Add health check retry/backoff support

#!/usr/bin/env python3
"""
Health check utility for HTTP and TCP endpoint monitoring.

Supports configurable retry/backoff for transient failures to reduce
false negatives in deployment validation and monitoring scenarios.
"""

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, List
from urllib.parse import urlparse

try:
    import urllib.request
    import urllib.error
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


class HealthStatus(Enum):
    """Health check result status."""
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


# Transient error types that warrant retry
TRANSIENT_SOCKET_ERRORS = (
    ConnectionRefusedError,
    ConnectionResetError,
    ConnectionAbortedError,
    socket.timeout,
    TimeoutError,
    OSError,  # Covers "Network is unreachable", etc.
)

TRANSIENT_HTTP_ERROR_CODES = {502, 503, 504}  # Bad Gateway, Service Unavailable, Gateway Timeout


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""
    status: HealthStatus
    message: str
    latency_ms: float = 0.0
    retry_attempts: int = 0
    total_retries: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert result to dictionary for JSON output."""
        result = {
            "status": self.status.value,
            "message": self.message,
            "latency_ms": round(self.latency_ms, 2),
        }
        if self.total_retries > 0:
            result["retry_attempts"] = self.retry_attempts
            result["max_retries"] = self.total_retries
        if self.details:
            result["details"] = self.details
        return result

    def to_text(self, include_retry_info: bool = False) -> str:
        """Convert result to text output."""
        base = f"{self.status.value}: {self.message}"
        if include_retry_info and self.retry_attempts > 0:
            base += f" (after {self.retry_attempts} retry/retries)"
        return base


def is_transient_error(error: Exception) -> bool:
    """Determine if an error is transient and should be retried."""
    if isinstance(error, TRANSIENT_SOCKET_ERRORS):
        return True
    if HAS_URLLIB and isinstance(error, urllib.error.URLError):
        # URLError wraps socket errors
        if isinstance(error.reason, TRANSIENT_SOCKET_ERRORS):
            return True
    if HAS_URLLIB and isinstance(error, urllib.error.HTTPError):
        if error.code in TRANSIENT_HTTP_ERROR_CODES:
            return True
    return False


def calculate_backoff(attempt: int, base_backoff: float, max_backoff: float = 30.0) -> float:
    """Calculate exponential backoff with jitter cap."""
    backoff = min(base_backoff * (2 ** attempt), max_backoff)
    return backoff


def check_tcp(
    host: str,
    port: int,
    timeout: float = 5.0,
    retries: int = 0,
    backoff: float = 1.0
) -> HealthCheckResult:
    """
    Perform TCP health check with optional retry/backoff.

    Args:
        host: Target hostname or IP address
        port: Target port number
        timeout: Connection timeout in seconds
        retries: Number of retry attempts for transient failures (default: 0)
        backoff: Base backoff interval in seconds between retries (default: 1.0)

    Returns:
        HealthCheckResult with status and timing information
    """
    attempt = 0
    last_error: Optional[Exception] = None
    total_start = time.monotonic()

    while attempt <= retries:
        if attempt > 0:
            sleep_time = calculate_backoff(attempt - 1, backoff)
            time.sleep(sleep_time)

        start = time.monotonic()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            elapsed = (time.monotonic() - start) * 1000

            return HealthCheckResult(
                status=HealthStatus.OK,
                message=f"TCP connection to {host}:{port} successful",
                latency_ms=elapsed,
                retry_attempts=attempt,
                total_retries=retries
            )
        except TRANSIENT_SOCKET_ERRORS as e:
            last_error = e
            if attempt < retries and is_transient_error(e):
                attempt += 1
                continue
            break
        except Exception as e:
            # Non-transient error, fail immediately
            elapsed = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                status=HealthStatus.CRITICAL,
                message=f"TCP connection to {host}:{port} failed: {e}",
                latency_ms=elapsed,
                retry_attempts=attempt,
                total_retries=retries
            )

    total_elapsed = (time.monotonic() - total_start) * 1000
    return HealthCheckResult(
        status=HealthStatus.CRITICAL,
        message=f"TCP connection to {host}:{port} failed after {attempt + 1} attempt(s): {last_error}",
        latency_ms=total_elapsed,
        retry_attempts=attempt,
        total_retries=retries,
        details={"error_type": type(last_error).__name__} if last_error else {}
    )


def check_http(
    url: str,
    timeout: float = 10.0,
    expected_status: int = 200,
    retries: int = 0,
    backoff: float = 1.0
) -> HealthCheckResult:
    """
    Perform HTTP health check with optional retry/backoff.

    Args:
        url: Target URL to check
        timeout: Request timeout in seconds
        expected_status: Expected HTTP status code (default: 200)
        retries: Number of retry attempts for transient failures (default: 0)
        backoff: Base backoff interval in seconds between retries (default: 1.0)

    Returns:
        HealthCheckResult with status and timing information
    """
    if not HAS_URLLIB:
        return HealthCheckResult(
            status=HealthStatus.UNKNOWN,
            message="urllib not available for HTTP checks"
        )

    attempt = 0
    last_error: Optional[Exception] = None
    total_start = time.monotonic()

    while attempt <= retries:
        if attempt > 0:
            sleep_time = calculate_backoff(attempt - 1, backoff)
            time.sleep(sleep_time)

        start = time.monotonic()
        try:
            request = urllib.request.Request(url, method='GET')
            request.add_header('User-Agent', 'zeroeye-health-check/1.0')

            with urllib.request.urlopen(request, timeout=timeout) as response:
                status_code = response.getcode()
                elapsed = (time.monotonic() - start) * 1000

                if status_code == expected_status:
                    return HealthCheckResult(
                        status=HealthStatus.OK,
                        message=f"HTTP {status_code} from {url}",
                        latency_ms=elapsed,
                        retry_attempts=attempt,
                        total_retries=retries,
                        details={"status_code": status_code}
                    )
                else:
                    return HealthCheckResult(
                        status=HealthStatus.WARNING,
                        message=f"HTTP {status_code} from {url} (expected {expected_status})",
                        latency_ms=elapsed,
                        retry_attempts=attempt,
                        total_retries=retries,
                        details={"status_code": status_code, "expected": expected_status}
                    )

        except urllib.error.HTTPError as e:
            elapsed = (time.monotonic() - start) * 1000
            if e.code in TRANSIENT_HTTP_ERROR_CODES and attempt < retries:
                last_error = e
                attempt += 1
                continue
            # Non-transient HTTP error or retries exhausted
            return HealthCheckResult(
                status=HealthStatus.CRITICAL,
                message=f"HTTP {e.code} from {url}" + (f" after {attempt + 1} attempt(s)" if attempt > 0 else ""),
                latency_ms=elapsed,
                retry_attempts=attempt,
                total_retries=retries,
                details={"status_code": e.code, "reason": e.reason}
            )

        except urllib.error.URLError as e:
            last_error = e
            if attempt < retries and is_transient_error(e):
                attempt += 1
                continue
            break

        except TRANSIENT_SOCKET_ERRORS as e:
            last_error = e
            if attempt < retries:
                attempt += 1
                continue
            break

        except Exception as e:
            # Non-transient error, fail immediately
            elapsed = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                status=HealthStatus.CRITICAL,
                message=f"HTTP check failed for {url}: {e}",
                latency_ms=elapsed,
                retry_attempts=attempt,
                total_retries=retries
            )

    total_elapsed = (time.monotonic() - total_start) * 1000
    error_msg = str(last_error.reason) if isinstance(last_error, urllib.error.URLError) else str(last_error)
    return HealthCheckResult(
        status=HealthStatus.CRITICAL,
        message=f"HTTP check failed for {url} after {attempt + 1} attempt(s): {error_msg}",
        latency_ms=total_elapsed,
        retry_attempts=attempt,
        total_retries=retries,
        details={"error_type": type(last_error).__name__} if last_error else {}
    )


def parse_target(target: str) -> Tuple[str, Optional[str], Optional[int]]:
    """
    Parse target string to determine check type.

    Returns:
        Tuple of (check_type, host, port) where check_type is 'http' or 'tcp'
    """
    if target.startswith(('http://', 'https://')):
        return ('http', target, None)

    # Check for host:port format
    if ':' in target:
        parts = target.rsplit(':', 1)
        try:
            port = int(parts[1])
            return ('tcp', parts[0], port)
        except ValueError:
            pass

    # Default to HTTP with scheme
    return ('http', f'http://{target}', None)


def main():
    """Main entry point for health check CLI."""
    parser = argparse.ArgumentParser(
        description='Health check utility for HTTP and TCP endpoints',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com                    # HTTP check
  %(prog)s localhost:6379                         # TCP check
  %(prog)s https://api.example.com --retries 3    # HTTP with 3 retries
  %(prog)s db.local:5432 --retries 5 --backoff 2  # TCP with retries and 2s backoff

Retry behavior:
  Transient failures (connection refused, timeouts, 502/503/504) are retried
  up to --retries times with exponential backoff starting at --backoff seconds.
  Non-transient failures (e.g., 404, 401) return immediately without retry.
"""
    )

    parser.add_argument(
        'target',
        help='Target to check (URL for HTTP, host:port for TCP)'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=float,
        default=10.0,
        help='Timeout in seconds (default: 10.0)'
    )
    parser.add_argument(
        '--expected-status', '-s',
        type=int,
        default=200,
        help='Expected HTTP status code (default: 200)'
    )
    parser.add_argument(
        '--retries', '-r',
        type=int,
        default=0,
        help='Number of retry attempts for transient failures (default: 0, no retries)'
    )
    parser.add_argument(
        '--backoff', '-b',
        type=float,
        default=1.0,
        help='Base backoff interval in seconds between retries (default: 1.0). Uses exponential backoff.'
    )
    parser.add_argument(
        '--json', '-j',
        action='store_true',
        help='Output results in JSON format (includes retry_attempts and max_retries when retries > 0)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Include retry information in text output'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.retries < 0:
        parser.error("--retries must be non-negative")
    if args.backoff <= 0:
        parser.error("--backoff must be positive")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    check_type, target, port = parse_target(args.target)

    if check_type == 'http':
        result = check_http(
            url=target,
            timeout=args.timeout,
            expected_status=args.expected_status,
            retries=args.retries,
            backoff=args.backoff
        )
    else:
        result = check_tcp(
            host=target,
            port=port,
            timeout=args.timeout,
            retries=args.retries,
            backoff=args.backoff
        )

    # Output results
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.to_text(include_retry_info=args.verbose or args.retries > 0))

    # Exit with appropriate code
    exit_codes = {
        HealthStatus.OK: 0,
        HealthStatus.WARNING: 1,
        HealthStatus.CRITICAL: 2,
        HealthStatus.UNKNOWN: 3
    }
    sys.exit(exit_codes.get(result.status, 3))


if __name__ == '__main__':
    main()