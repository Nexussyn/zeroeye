# Fix for Issue #4: [$50 BOUNTY] [Python] Add retry/backoff to health_check.py for transient failures

#!/usr/bin/env python3
"""
Health check module with retry/backoff for transient failures.

Performs system health checks for CPU, memory, disk, and network
with exponential backoff retry logic for resilience against
transient failures.
"""

import functools
import logging
import os
import socket
import time
from typing import Callable, Tuple, Any, Optional, Type, Union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type alias for health check result
HealthCheckResult = Tuple[str, str, Any]

# Transient exceptions that should trigger retries
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
    exponential_base: float = DEFAULT_EXPONENTIAL_BASE,
    exceptions: Tuple[Type[Exception], ...] = TRANSIENT_EXCEPTIONS,
) -> Callable:
    """
    Decorator that implements retry with exponential backoff.
    
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
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(
                            f"{func.__name__} succeeded on attempt {attempt + 1}"
                        )
                    return result
                except exceptions as e:
                    last_exception = e
                    
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
            
            # All retries exhausted - return error result preserving format
            error_detail = f"Failed after {max_retries} attempts: {last_exception}"
            return ("error", error_detail, None)
        
        return wrapper
    return decorator


def _get_cpu_percent() -> float:
    """
    Get CPU usage percentage using /proc/stat.
    
    Returns:
        CPU usage as a percentage (0-100)
    """
    def read_cpu_stats():
        with open('/proc/stat', 'r') as f:
            line = f.readline()
            parts = line.split()
            # cpu user nice system idle iowait irq softirq steal guest guest_nice
            return [int(x) for x in parts[1:]]
    
    stats1 = read_cpu_stats()
    time.sleep(0.1)  # Brief sample interval
    stats2 = read_cpu_stats()
    
    # Calculate deltas
    idle1 = stats1[3] + stats1[4]  # idle + iowait
    idle2 = stats2[3] + stats2[4]
    
    total1 = sum(stats1[:8])
    total2 = sum(stats2[:8])
    
    total_delta = total2 - total1
    idle_delta = idle2 - idle1
    
    if total_delta == 0:
        return 0.0
    
    return ((total_delta - idle_delta) / total_delta) * 100


def _get_memory_info() -> Tuple[int, int, float]:
    """
    Get memory information from /proc/meminfo.
    
    Returns:
        Tuple of (total_kb, available_kb, used_percent)
    """
    meminfo = {}
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            parts = line.split()
            key = parts[0].rstrip(':')
            value = int(parts[1])
            meminfo[key] = value
    
    total = meminfo['MemTotal']
    available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
    used_percent = ((total - available) / total) * 100
    
    return total, available, used_percent


def _get_disk_usage(path: str = '/') -> Tuple[int, int, float]:
    """
    Get disk usage for specified path.
    
    Args:
        path: Filesystem path to check
    
    Returns:
        Tuple of (total_bytes, free_bytes, used_percent)
    """
    stat = os.statvfs(path)
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bavail * stat.f_frsize
    used_percent = ((total - free) / total) * 100 if total > 0 else 0
    
    return total, free, used_percent


def _get_load_average() -> Tuple[float, float, float]:
    """
    Get system load averages.
    
    Returns:
        Tuple of (1min, 5min, 15min) load averages
    """
    return os.getloadavg()


@retry_with_backoff()
def check_cpu_health(threshold: float = 90.0) -> HealthCheckResult:
    """
    Check CPU usage health.
    
    Args:
        threshold: CPU usage percentage threshold for warning
    
    Returns:
        Tuple of (status, detail, value)
    """
    cpu_percent = _get_cpu_percent()
    
    if cpu_percent >= threshold:
        status = "warning"
        detail = f"CPU usage is high: {cpu_percent:.1f}%"
    else:
        status = "ok"
        detail = f"CPU usage is normal: {cpu_percent:.1f}%"
    
    return (status, detail, cpu_percent)


@retry_with_backoff()
def check_memory_usage(threshold: float = 90.0) -> HealthCheckResult:
    """
    Check memory usage health.
    
    Args:
        threshold: Memory usage percentage threshold for warning
    
    Returns:
        Tuple of (status, detail, value)
    """
    total, available, used_percent = _get_memory_info()
    
    if used_percent >= threshold:
        status = "warning"
        detail = f"Memory usage is high: {used_percent:.1f}%"
    else:
        status = "ok"
        detail = f"Memory usage is normal: {used_percent:.1f}%"
    
    return (status, detail, used_percent)


@retry_with_backoff()
def check_disk_usage(path: str = '/', threshold: float = 90.0) -> HealthCheckResult:
    """
    Check disk usage health.
    
    Args:
        path: Filesystem path to check
        threshold: Disk usage percentage threshold for warning
    
    Returns:
        Tuple of (status, detail, value)
    """
    total, free, used_percent = _get_disk_usage(path)
    
    if used_percent >= threshold:
        status = "warning"
        detail = f"Disk usage is high on {path}: {used_percent:.1f}%"
    else:
        status = "ok"
        detail = f"Disk usage is normal on {path}: {used_percent:.1f}%"
    
    return (status, detail, used_percent)


@retry_with_backoff()
def check_load_average(threshold_multiplier: float = 1.0) -> HealthCheckResult:
    """
    Check system load average health.
    
    Args:
        threshold_multiplier: Multiplier for CPU count to determine threshold
    
    Returns:
        Tuple of (status, detail, value)
    """
    load1, load5, load15 = _get_load_average()
    cpu_count = os.cpu_count() or 1
    threshold = cpu_count * threshold_multiplier
    
    if load1 >= threshold:
        status = "warning"
        detail = f"Load average is high: {load1:.2f} (threshold: {threshold:.2f})"
    else:
        status = "ok"
        detail = f"Load average is normal: {load1:.2f}"
    
    return (status, detail, load1)


@retry_with_backoff()
def check_tcp_port(
    host: str = 'localhost',
    port: int = 80,
    timeout: float = 5.0
) -> HealthCheckResult:
    """
    Check if a TCP port is accessible.
    
    Args:
        host: Target hostname or IP
        port: Target port number
        timeout: Connection timeout in seconds
    
    Returns:
        Tuple of (status, detail, value)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            status = "ok"
            detail = f"Port {port} on {host} is open"
            value = True
        else:
            status = "error"
            detail = f"Port {port} on {host} is closed (error code: {result})"
            value = False
    finally:
        sock.close()
    
    return (status, detail, value)


def check_system_health(
    cpu_threshold: float = 90.0,
    memory_threshold: float = 90.0,
    disk_threshold: float = 90.0,
    disk_path: str = '/',
    load_threshold_multiplier: float = 1.0,
    tcp_checks: Optional[list] = None,
) -> dict:
    """
    Perform comprehensive system health check.
    
    This is the main orchestrator that runs all health checks
    with retry/backoff logic for transient failures.
    
    Args:
        cpu_threshold: CPU usage warning threshold
        memory_threshold: Memory usage warning threshold
        disk_threshold: Disk usage warning threshold
        disk_path: Filesystem path to check for disk usage
        load_threshold_multiplier: Load average threshold multiplier
        tcp_checks: List of (host, port) tuples to check
    
    Returns:
        Dictionary containing all health check results
    """
    results = {
        'timestamp': time.time(),
        'checks': {},
        'overall_status': 'ok',
    }
    
    # Run all health checks
    checks = [
        ('cpu', lambda: check_cpu_health(cpu_threshold)),
        ('memory', lambda: check_memory_usage(memory_threshold)),
        ('disk', lambda: check_disk_usage(disk_path, disk_threshold)),
        ('load_average', lambda: check_load_average(load_threshold_multiplier)),
    ]
    
    # Add TCP port checks if specified
    if tcp_checks:
        for host, port in tcp_checks:
            check_name = f'tcp_{host}_{port}'
            checks.append(
                (check_name, lambda h=host, p=port: check_tcp_port(h, p))
            )
    
    # Execute all checks
    for check_name, check_func in checks:
        try:
            status, detail, value = check_func()
            results['checks'][check_name] = {
                'status': status,
                'detail': detail,
                'value': value,
            }
            
            # Update overall status (error > warning > ok)
            if status == 'error':
                results['overall_status'] = 'error'
            elif status == 'warning' and results['overall_status'] != 'error':
                results['overall_status'] = 'warning'
                
        except Exception as e:
            logger.error(f"Unexpected error in {check_name}: {e}")
            results['checks'][check_name] = {
                'status': 'error',
                'detail': f'Unexpected error: {e}',
                'value': None,
            }
            results['overall_status'] = 'error'
    
    return results


if __name__ == '__main__':
    import json
    
    print("Running system health checks...")
    health_results = check_system_health(
        tcp_checks=[('localhost', 22)]  # Example: check SSH port
    )
    print(json.dumps(health_results, indent=2))