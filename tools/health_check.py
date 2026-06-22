# Fix for Issue #4: [$50 BOUNTY] [Python] Add retry/backoff to health_check.py for transient failures

#!/usr/bin/env python3
"""
Health check module with retry/backoff for transient failures.

Performs system health checks for CPU, memory, disk, and network
with exponential backoff retry logic for transient failures.
"""

import functools
import logging
import os
import socket
import time
from typing import Callable, Tuple, Any, Optional, List, Type

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type alias for health check result
HealthCheckResult = Tuple[str, str, Any]

# Transient exceptions that should trigger retry
TRANSIENT_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    socket.timeout,
    OSError,
    ConnectionError,
    TimeoutError,
)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds
DEFAULT_EXPONENTIAL_BASE = 2


def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    exponential_base: int = DEFAULT_EXPONENTIAL_BASE,
    exceptions: Tuple[Type[Exception], ...] = TRANSIENT_EXCEPTIONS,
) -> Callable:
    """
    Decorator that implements retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (minimum 3)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exception types to catch and retry
    
    Returns:
        Decorated function with retry logic
    """
    # Ensure minimum of 3 retries as per requirements
    max_retries = max(max_retries, 3)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> HealthCheckResult:
            last_exception: Optional[Exception] = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    # Don't sleep after the last attempt
                    if attempt < max_retries - 1:
                        # Calculate delay with exponential backoff
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}): "
                            f"{type(e).__name__}: {e}. Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} attempts: "
                            f"{type(e).__name__}: {e}"
                        )
            
            # All retries exhausted - return error result
            error_msg = f"Failed after {max_retries} retries: {last_exception}"
            return ("error", error_msg, None)
        
        return wrapper
    return decorator


@retry_with_backoff()
def check_cpu_health() -> HealthCheckResult:
    """
    Check CPU health by examining load average.
    
    Returns:
        Tuple of (status, detail, value) where:
        - status: 'ok', 'warning', 'critical', or 'error'
        - detail: Human-readable description
        - value: The measured value (load average)
    """
    try:
        load_avg = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        
        # Use 1-minute load average normalized by CPU count
        load_per_cpu = load_avg[0] / cpu_count
        
        if load_per_cpu < 0.7:
            status = "ok"
            detail = f"CPU load normal: {load_avg[0]:.2f} ({load_per_cpu:.2f} per CPU)"
        elif load_per_cpu < 1.0:
            status = "warning"
            detail = f"CPU load elevated: {load_avg[0]:.2f} ({load_per_cpu:.2f} per CPU)"
        else:
            status = "critical"
            detail = f"CPU load high: {load_avg[0]:.2f} ({load_per_cpu:.2f} per CPU)"
        
        return (status, detail, load_avg[0])
    
    except AttributeError:
        # os.getloadavg() not available on Windows
        return ("ok", "Load average not available on this platform", None)


@retry_with_backoff()
def check_load_average() -> HealthCheckResult:
    """
    Check system load average (1, 5, 15 minute averages).
    
    Returns:
        Tuple of (status, detail, value)
    """
    try:
        load_avg = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        
        # Check all three load averages
        load_1, load_5, load_15 = load_avg
        normalized_1 = load_1 / cpu_count
        
        if normalized_1 < 0.7:
            status = "ok"
        elif normalized_1 < 1.0:
            status = "warning"
        else:
            status = "critical"
        
        detail = f"Load avg (1/5/15 min): {load_1:.2f}/{load_5:.2f}/{load_15:.2f}"
        return (status, detail, load_avg)
    
    except AttributeError:
        return ("ok", "Load average not available on this platform", None)


@retry_with_backoff()
def check_memory_usage() -> HealthCheckResult:
    """
    Check memory usage by reading /proc/meminfo or using fallback.
    
    Returns:
        Tuple of (status, detail, value) where value is usage percentage
    """
    try:
        # Try reading from /proc/meminfo (Linux)
        with open('/proc/meminfo', 'r') as f:
            meminfo = {}
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    # Extract numeric value (in kB)
                    value_parts = parts[1].strip().split()
                    if value_parts:
                        try:
                            meminfo[key] = int(value_parts[0])
                        except ValueError:
                            continue
        
        total = meminfo.get('MemTotal', 0)
        available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
        
        if total == 0:
            return ("error", "Could not determine total memory", None)
        
        used_percent = ((total - available) / total) * 100
        
        if used_percent < 70:
            status = "ok"
            detail = f"Memory usage normal: {used_percent:.1f}%"
        elif used_percent < 90:
            status = "warning"
            detail = f"Memory usage elevated: {used_percent:.1f}%"
        else:
            status = "critical"
            detail = f"Memory usage critical: {used_percent:.1f}%"
        
        return (status, detail, used_percent)
    
    except FileNotFoundError:
        # Fallback for non-Linux systems
        return ("ok", "Memory check not available on this platform", None)


@retry_with_backoff()
def check_disk_usage(path: str = '/') -> HealthCheckResult:
    """
    Check disk usage for the specified path.
    
    Args:
        path: Filesystem path to check (default: root)
    
    Returns:
        Tuple of (status, detail, value) where value is usage percentage
    """
    try:
        stat = os.statvfs(path)
        
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        
        if total == 0:
            return ("error", f"Could not determine disk size for {path}", None)
        
        used_percent = (used / total) * 100
        
        if used_percent < 70:
            status = "ok"
            detail = f"Disk usage for {path}: {used_percent:.1f}%"
        elif used_percent < 90:
            status = "warning"
            detail = f"Disk usage elevated for {path}: {used_percent:.1f}%"
        else:
            status = "critical"
            detail = f"Disk usage critical for {path}: {used_percent:.1f}%"
        
        return (status, detail, used_percent)
    
    except AttributeError:
        # os.statvfs not available on Windows
        return ("ok", f"Disk check not available on this platform for {path}", None)


@retry_with_backoff()
def check_tcp_port(host: str = 'localhost', port: int = 80, timeout: float = 5.0) -> HealthCheckResult:
    """
    Check if a TCP port is accessible.
    
    Args:
        host: Hostname or IP address to check
        port: Port number to check
        timeout: Connection timeout in seconds
    
    Returns:
        Tuple of (status, detail, value) where value is response time in ms
    """
    start_time = time.time()
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        result = sock.connect_ex((host, port))
        response_time = (time.time() - start_time) * 1000  # Convert to ms
        
        sock.close()
        
        if result == 0:
            status = "ok"
            detail = f"Port {host}:{port} is open (response: {response_time:.1f}ms)"
            return (status, detail, response_time)
        else:
            status = "critical"
            detail = f"Port {host}:{port} is closed or unreachable"
            return (status, detail, None)
    
    except socket.timeout:
        # Re-raise to trigger retry
        raise
    except socket.gaierror as e:
        # DNS resolution error - not transient, don't retry
        return ("error", f"DNS resolution failed for {host}: {e}", None)


def check_system_health(
    include_network: bool = True,
    network_host: str = 'localhost',
    network_port: int = 80,
    disk_paths: Optional[List[str]] = None
) -> dict:
    """
    Perform comprehensive system health check.
    
    Args:
        include_network: Whether to include TCP port check
        network_host: Host for network check
        network_port: Port for network check
        disk_paths: List of disk paths to check (default: ['/'])
    
    Returns:
        Dictionary with health check results for each component
    """
    if disk_paths is None:
        disk_paths = ['/']
    
    results = {}
    
    # CPU health check
    logger.info("Checking CPU health...")
    results['cpu'] = check_cpu_health()
    
    # Load average check
    logger.info("Checking load average...")
    results['load_average'] = check_load_average()
    
    # Memory check
    logger.info("Checking memory usage...")
    results['memory'] = check_memory_usage()
    
    # Disk checks
    for path in disk_paths:
        logger.info(f"Checking disk usage for {path}...")
        results[f'disk_{path}'] = check_disk_usage(path)
    
    # Network check
    if include_network:
        logger.info(f"Checking TCP port {network_host}:{network_port}...")
        results['network'] = check_tcp_port(network_host, network_port)
    
    # Calculate overall status
    statuses = [r[0] for r in results.values()]
    if 'critical' in statuses:
        overall = 'critical'
    elif 'error' in statuses:
        overall = 'error'
    elif 'warning' in statuses:
        overall = 'warning'
    else:
        overall = 'ok'
    
    results['overall'] = (overall, f"System health: {overall}", None)
    
    return results


def format_health_report(results: dict) -> str:
    """
    Format health check results as a human-readable report.
    
    Args:
        results: Dictionary of health check results
    
    Returns:
        Formatted string report
    """
    lines = ["=" * 50, "SYSTEM HEALTH REPORT", "=" * 50, ""]
    
    status_icons = {
        'ok': '✓',
        'warning': '⚠',
        'critical': '✗',
        'error': '!'
    }
    
    for component, (status, detail, value) in results.items():
        icon = status_icons.get(status, '?')
        lines.append(f"[{icon}] {component.upper()}: {status}")
        lines.append(f"    {detail}")
        if value is not None:
            lines.append(f"    Value: {value}")
        lines.append("")
    
    lines.append("=" * 50)
    return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='System Health Check')
    parser.add_argument('--no-network', action='store_true',
                        help='Skip network checks')
    parser.add_argument('--host', default='localhost',
                        help='Host for network check')
    parser.add_argument('--port', type=int, default=80,
                        help='Port for network check')
    parser.add_argument('--disk', action='append', dest='disks',
                        help='Disk paths to check (can be specified multiple times)')
    parser.add_argument('--json', action='store_true',
                        help='Output in JSON format')
    
    args = parser.parse_args()
    
    results = check_system_health(
        include_network=not args.no_network,
        network_host=args.host,
        network_port=args.port,
        disk_paths=args.disks
    )
    
    if args.json:
        import json
        # Convert tuples to dicts for JSON serialization
        json_results = {
            k: {'status': v[0], 'detail': v[1], 'value': v[2]}
            for k, v in results.items()
        }
        print(json.dumps(json_results, indent=2))
    else:
        print(format_health_report(results))