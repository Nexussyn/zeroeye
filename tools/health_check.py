# Fix for Issue #1: [ BOUNTY] [Python] Add retry mechanism with exponential backoff to health check tool

#!/usr/bin/env python3
"""
Health Check Tool with Retry Mechanism and Exponential Backoff

This tool performs health checks on HTTP services and TCP ports with
configurable retry attempts and exponential backoff to prevent false
alarms due to transient network issues.
"""

import argparse
import json
import socket
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from enum import Enum


class HealthStatus(Enum):
    """Health check status codes."""
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


def log_message(message: str, json_output: bool = False) -> None:
    """Log a message to stderr if not in JSON mode."""
    if not json_output:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}", file=sys.stderr)


def calculate_backoff(attempt: int, base_backoff: float) -> float:
    """
    Calculate exponential backoff delay.
    
    Args:
        attempt: Current attempt number (0-indexed)
        base_backoff: Base backoff time in seconds
    
    Returns:
        Delay in seconds before next retry
    """
    return base_backoff * (2 ** attempt)


def retry_with_backoff(
    func,
    retries: int,
    backoff: float,
    json_output: bool,
    operation_name: str
) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Execute a function with retry and exponential backoff.
    
    Args:
        func: Function to execute, should return (success, error_message, response_time)
        retries: Maximum number of retry attempts
        backoff: Base backoff time in seconds
        json_output: Whether output is in JSON format (suppresses logs)
        operation_name: Name of the operation for logging
    
    Returns:
        Tuple of (success, error_message, response_time)
    """
    last_error = None
    last_response_time = None
    
    for attempt in range(retries):
        success, error, response_time = func()
        last_response_time = response_time
        
        if success:
            if attempt > 0:
                log_message(
                    f"{operation_name}: Succeeded on attempt {attempt + 1}/{retries}",
                    json_output
                )
            return True, None, response_time
        
        last_error = error
        
        # Don't sleep after the last attempt
        if attempt < retries - 1:
            delay = calculate_backoff(attempt, backoff)
            log_message(
                f"{operation_name}: Attempt {attempt + 1}/{retries} failed: {error}. "
                f"Retrying in {delay:.2f}s...",
                json_output
            )
            time.sleep(delay)
        else:
            log_message(
                f"{operation_name}: Attempt {attempt + 1}/{retries} failed: {error}. "
                f"No more retries.",
                json_output
            )
    
    return False, last_error, last_response_time


def check_tcp_port(
    host: str,
    port: int,
    timeout: float = 5.0,
    retries: int = 3,
    backoff: float = 2.0,
    json_output: bool = False
) -> Dict[str, Any]:
    """
    Check if a TCP port is open and accepting connections.
    
    Args:
        host: Hostname or IP address to check
        port: Port number to check
        timeout: Connection timeout in seconds
        retries: Number of retry attempts
        backoff: Base backoff time in seconds for exponential backoff
        json_output: Whether to suppress retry logging for JSON output
    
    Returns:
        Dictionary containing health check results
    """
    result = {
        "check_type": "tcp",
        "host": host,
        "port": port,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "retries_configured": retries,
        "backoff_configured": backoff
    }
    
    def attempt_connection() -> Tuple[bool, Optional[str], Optional[float]]:
        """Single connection attempt."""
        start_time = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.close()
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            return True, None, response_time
        except socket.timeout:
            return False, "Connection timed out", None
        except socket.gaierror as e:
            return False, f"DNS resolution failed: {e}", None
        except ConnectionRefusedError:
            return False, "Connection refused", None
        except OSError as e:
            return False, f"OS error: {e}", None
        except Exception as e:
            return False, f"Unexpected error: {e}", None
    
    operation_name = f"TCP check {host}:{port}"
    success, error, response_time = retry_with_backoff(
        attempt_connection,
        retries,
        backoff,
        json_output,
        operation_name
    )
    
    if success:
        result["status"] = "OK"
        result["status_code"] = HealthStatus.OK.value
        result["message"] = f"TCP port {port} is open on {host}"
        result["response_time_ms"] = round(response_time, 2) if response_time else None
    else:
        result["status"] = "CRITICAL"
        result["status_code"] = HealthStatus.CRITICAL.value
        result["message"] = f"TCP port {port} is not accessible on {host}: {error}"
        result["error"] = error
    
    return result


def check_http_service(
    url: str,
    timeout: float = 10.0,
    expected_status: int = 200,
    retries: int = 3,
    backoff: float = 2.0,
    json_output: bool = False
) -> Dict[str, Any]:
    """
    Check if an HTTP service is responding.
    
    Args:
        url: URL to check
        timeout: Request timeout in seconds
        expected_status: Expected HTTP status code
        retries: Number of retry attempts
        backoff: Base backoff time in seconds for exponential backoff
        json_output: Whether to suppress retry logging for JSON output
    
    Returns:
        Dictionary containing health check results
    """
    result = {
        "check_type": "http",
        "url": url,
        "expected_status": expected_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "retries_configured": retries,
        "backoff_configured": backoff
    }
    
    def attempt_request() -> Tuple[bool, Optional[str], Optional[float]]:
        """Single HTTP request attempt."""
        start_time = time.time()
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "HealthCheck/1.0"}
            )
            response = urllib.request.urlopen(request, timeout=timeout)
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            status_code = response.getcode()
            
            if status_code == expected_status:
                return True, None, response_time
            else:
                return False, f"Unexpected status code: {status_code}", response_time
                
        except urllib.error.HTTPError as e:
            response_time = (time.time() - start_time) * 1000
            if e.code == expected_status:
                return True, None, response_time
            return False, f"HTTP error: {e.code} {e.reason}", response_time
        except urllib.error.URLError as e:
            return False, f"URL error: {e.reason}", None
        except socket.timeout:
            return False, "Request timed out", None
        except Exception as e:
            return False, f"Unexpected error: {e}", None
    
    operation_name = f"HTTP check {url}"
    success, error, response_time = retry_with_backoff(
        attempt_request,
        retries,
        backoff,
        json_output,
        operation_name
    )
    
    if success:
        result["status"] = "OK"
        result["status_code"] = HealthStatus.OK.value
        result["message"] = f"HTTP service at {url} is healthy"
        result["response_time_ms"] = round(response_time, 2) if response_time else None
    else:
        result["status"] = "CRITICAL"
        result["status_code"] = HealthStatus.CRITICAL.value
        result["message"] = f"HTTP service at {url} is not healthy: {error}"
        result["error"] = error
        if response_time:
            result["response_time_ms"] = round(response_time, 2)
    
    return result


def main():
    """Main entry point for the health check tool."""
    parser = argparse.ArgumentParser(
        description="Health check tool with retry mechanism and exponential backoff",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check HTTP service with default retries
  python health_check.py --http https://example.com
  
  # Check TCP port with custom retries and backoff
  python health_check.py --tcp localhost:5432 --retries 5 --backoff 1.5
  
  # JSON output for automation
  python health_check.py --http https://api.example.com --json
  
  # Multiple checks
  python health_check.py --http https://example.com --tcp localhost:6379
        """
    )
    
    parser.add_argument(
        "--http",
        action="append",
        metavar="URL",
        help="HTTP URL to check (can be specified multiple times)"
    )
    parser.add_argument(
        "--tcp",
        action="append",
        metavar="HOST:PORT",
        help="TCP host:port to check (can be specified multiple times)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout in seconds for each connection attempt (default: 10)"
    )
    parser.add_argument(
        "--expected-status",
        type=int,
        default=200,
        help="Expected HTTP status code (default: 200)"
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retry attempts (default: 3)"
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=2.0,
        help="Base backoff time in seconds for exponential backoff (default: 2.0)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.http and not args.tcp:
        parser.error("At least one --http or --tcp check must be specified")
    
    if args.retries < 1:
        parser.error("--retries must be at least 1")
    
    if args.backoff < 0:
        parser.error("--backoff must be non-negative")
    
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    
    results = []
    overall_status = HealthStatus.OK
    
    # Perform HTTP checks
    if args.http:
        for url in args.http:
            result = check_http_service(
                url=url,
                timeout=args.timeout,
                expected_status=args.expected_status,
                retries=args.retries,
                backoff=args.backoff,
                json_output=args.json
            )
            results.append(result)
            
            if result["status_code"] == HealthStatus.CRITICAL.value:
                overall_status = HealthStatus.CRITICAL
            elif result["status_code"] == HealthStatus.WARNING.value and overall_status != HealthStatus.CRITICAL:
                overall_status = HealthStatus.WARNING
    
    # Perform TCP checks
    if args.tcp:
        for tcp_target in args.tcp:
            try:
                if ":" in tcp_target:
                    host, port_str = tcp_target.rsplit(":", 1)
                    port = int(port_str)
                else:
                    parser.error(f"Invalid TCP target format: {tcp_target}. Use HOST:PORT")
                    continue
            except ValueError:
                parser.error(f"Invalid port number in: {tcp_target}")
                continue
            
            result = check_tcp_port(
                host=host,
                port=port,
                timeout=args.timeout,
                retries=args.retries,
                backoff=args.backoff,
                json_output=args.json
            )
            results.append(result)
            
            if result["status_code"] == HealthStatus.CRITICAL.value:
                overall_status = HealthStatus.CRITICAL
            elif result["status_code"] == HealthStatus.WARNING.value and overall_status != HealthStatus.CRITICAL:
                overall_status = HealthStatus.WARNING
    
    # Output results
    if args.json:
        output = {
            "overall_status": overall_status.name,
            "overall_status_code": overall_status.value,
            "checks": results,
            "summary": {
                "total": len(results),
                "ok": sum(1 for r in results if r["status_code"] == HealthStatus.OK.value),
                "warning": sum(1 for r in results if r["status_code"] == HealthStatus.WARNING.value),
                "critical": sum(1 for r in results if r["status_code"] == HealthStatus.CRITICAL.value)
            }
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'='*60}")
        print("HEALTH CHECK RESULTS")
        print(f"{'='*60}")
        
        for result in results:
            status_symbol = "✓" if result["status"] == "OK" else "✗"
            print(f"\n{status_symbol} [{result['status']}] {result['check_type'].upper()}: {result.get('url') or f\"{result['host']}:{result['port']}\"}")
            print(f"  Message: {result['message']}")
            if result.get('response_time_ms'):
                print(f"  Response time: {result['response_time_ms']}ms")
            if result.get('error'):
                print(f"  Error: {result['error']}")
        
        print(f"\n{'='*60}")
        print(f"Overall Status: {overall_status.name}")
        ok_count = sum(1 for r in results if r["status_code"] == HealthStatus.OK.value)
        print(f"Checks: {ok_count}/{len(results)} passed")
        print(f"{'='*60}\n")
    
    # Exit with appropriate status code
    sys.exit(overall_status.value)


if __name__ == "__main__":
    main()