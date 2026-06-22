# Fix for Issue #4: [$50 BOUNTY] [Python] Add retry/backoff to health_check.py for transient failures

#!/usr/bin/env python3
"""
Health check module for system monitoring.
Performs health checks for CPU, memory, disk, and network with retry/backoff support.
"""

import functools
import os
import socket
import time
from typing import Callable, Tuple, Any, Optional

# Transient exceptions that should trigger retry
TRANSIENT_EXCEPTIONS = (
    socket.timeout,
    OSError,
    ConnectionError,
    TimeoutError,
)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 0.5  # seconds
DEFAULT_MAX_DELAY = 10.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0


def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    exceptions: Tuple = TRANSIENT_EXCEPTIONS,
) -> Callable:
    """
    Decorator that implements retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (minimum 3)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for exponential backoff
        exceptions: Tuple of exception types to catch and retry
        
    Returns:
        Decorated function with retry logic
    """
    # Enforce minimum 3 retries as per requirements
    max_retries = max(max_retries, 3)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = base_delay
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    # Don't sleep after the last attempt
                    if attempt < max_retries - 1:
                        # Calculate delay with exponential backoff
                        sleep_time = min(delay, max_delay)
                        time.sleep(sleep_time)
                        delay *= backoff_factor
            
            # All retries exhausted - return failure status
            # Preserve existing result format: (status, detail, value)
            error_detail = f"Failed after {max_retries} retries: {type(last_exception).__name__}: {str(last_exception)}"
            return ("unhealthy", error_detail, None)
        
        return wrapper
    return decorator


def _read_proc_stat() -> dict:
    """Read CPU statistics from /proc/stat."""
    cpu_stats = {}
    with open('/proc/stat', 'r') as f:
        for line in f:
            if line.startswith('cpu '):
                parts = line.split()
                cpu_stats['user'] = int(parts[1])
                cpu_stats['nice'] = int(parts[2])
                cpu_stats['system'] = int(parts[3])
                cpu_stats['idle'] = int(parts[4])
                cpu_stats['iowait'] = int(parts[5]) if len(parts) > 5 else 0
                break
    return cpu_stats


def _read_proc_meminfo() -> dict:
    """Read memory statistics from /proc/meminfo."""
    mem_stats = {}
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            parts = line.split()
            key = parts[0].rstrip(':')
            value = int(parts[1])
            mem_stats[key] = value
    return mem_stats


@retry_with_backoff()
def check_cpu_health(threshold: float = 90.0) -> Tuple[str, str, Optional[float]]:
    """
    Check CPU health by measuring utilization.
    
    Args:
        threshold: CPU usage percentage threshold for unhealthy status
        
    Returns:
        Tuple of (status, detail, value) where:
        - status: 'healthy' or 'unhealthy'
        - detail: Human-readable description
        - value: CPU usage percentage or None on error
    """
    try:
        # Take two samples to calculate CPU usage
        stat1 = _read_proc_stat()
        time.sleep(0.1)
        stat2 = _read_proc_stat()
        
        # Calculate deltas
        total1 = sum(stat1.values())
        total2 = sum(stat2.values())
        idle1 = stat1['idle'] + stat1.get('iowait', 0)
        idle2 = stat2['idle'] + stat2.get('iowait', 0)
        
        total_delta = total2 - total1
        idle_delta = idle2 - idle1
        
        if total_delta == 0:
            return ("healthy", "CPU idle", 0.0)
        
        cpu_usage = ((total_delta - idle_delta) / total_delta) * 100
        
        if cpu_usage >= threshold:
            return ("unhealthy", f"CPU usage high: {cpu_usage:.1f}%", cpu_usage)
        
        return ("healthy", f"CPU usage: {cpu_usage:.1f}%", cpu_usage)
        
    except FileNotFoundError:
        # Fallback for non-Linux systems
        load_avg = os.getloadavg()[0]
        cpu_count = os.cpu_count() or 1
        usage_estimate = (load_avg / cpu_count) * 100
        
        if usage_estimate >= threshold:
            return ("unhealthy", f"Estimated CPU usage high: {usage_estimate:.1f}%", usage_estimate)
        return ("healthy", f"Estimated CPU usage: {usage_estimate:.1f}%", usage_estimate)


@retry_with_backoff()
def check_load_average(threshold_multiplier: float = 2.0) -> Tuple[str, str, Optional[float]]:
    """
    Check system load average.
    
    Args:
        threshold_multiplier: Multiplier of CPU count for unhealthy threshold
        
    Returns:
        Tuple of (status, detail, value)
    """
    load_1, load_5, load_15 = os.getloadavg()
    cpu_count = os.cpu_count() or 1
    threshold = cpu_count * threshold_multiplier
    
    if load_1 >= threshold:
        return (
            "unhealthy",
            f"Load average high: {load_1:.2f} (threshold: {threshold:.2f})",
            load_1
        )
    
    return (
        "healthy",
        f"Load average: {load_1:.2f}/{load_5:.2f}/{load_15:.2f}",
        load_1
    )


@retry_with_backoff()
def check_memory_usage(threshold: float = 90.0) -> Tuple[str, str, Optional[float]]:
    """
    Check memory usage.
    
    Args:
        threshold: Memory usage percentage threshold for unhealthy status
        
    Returns:
        Tuple of (status, detail, value)
    """
    try:
        mem_stats = _read_proc_meminfo()
        
        total = mem_stats.get('MemTotal', 0)
        free = mem_stats.get('MemFree', 0)
        buffers = mem_stats.get('Buffers', 0)
        cached = mem_stats.get('Cached', 0)
        
        if total == 0:
            return ("unhealthy", "Unable to read memory info", None)
        
        # Available memory includes free + buffers + cached
        available = free + buffers + cached
        used_percent = ((total - available) / total) * 100
        
        if used_percent >= threshold:
            return (
                "unhealthy",
                f"Memory usage high: {used_percent:.1f}%",
                used_percent
            )
        
        return ("healthy", f"Memory usage: {used_percent:.1f}%", used_percent)
        
    except FileNotFoundError:
        return ("unhealthy", "Memory info not available (non-Linux system)", None)


@retry_with_backoff()
def check_disk_usage(path: str = "/", threshold: float = 90.0) -> Tuple[str, str, Optional[float]]:
    """
    Check disk usage for a given path.
    
    Args:
        path: Filesystem path to check
        threshold: Disk usage percentage threshold for unhealthy status
        
    Returns:
        Tuple of (status, detail, value)
    """
    stat = os.statvfs(path)
    
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bavail * stat.f_frsize
    
    if total == 0:
        return ("unhealthy", f"Unable to read disk info for {path}", None)
    
    used_percent = ((total - free) / total) * 100
    
    if used_percent >= threshold:
        return (
            "unhealthy",
            f"Disk usage high on {path}: {used_percent:.1f}%",
            used_percent
        )
    
    return ("healthy", f"Disk usage on {path}: {used_percent:.1f}%", used_percent)


@retry_with_backoff()
def check_tcp_port(
    host: str = "127.0.0.1",
    port: int = 80,
    timeout: float = 5.0
) -> Tuple[str, str, Optional[bool]]:
    """
    Check if a TCP port is accessible.
    
    Args:
        host: Host to connect to
        port: Port number to check
        timeout: Connection timeout in seconds
        
    Returns:
        Tuple of (status, detail, value)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            return ("healthy", f"Port {host}:{port} is accessible", True)
        else:
            return ("unhealthy", f"Port {host}:{port} is not accessible (error: {result})", False)
    finally:
        sock.close()


def check_system_health(
    cpu_threshold: float = 90.0,
    memory_threshold: float = 90.0,
    disk_threshold: float = 90.0,
    disk_path: str = "/",
    load_threshold_multiplier: float = 2.0,
    tcp_checks: Optional[list] = None,
) -> dict:
    """
    Perform comprehensive system health check.
    
    Args:
        cpu_threshold: CPU usage threshold percentage
        memory_threshold: Memory usage threshold percentage
        disk_threshold: Disk usage threshold percentage
        disk_path: Path for disk check
        load_threshold_multiplier: Load average threshold multiplier
        tcp_checks: List of (host, port) tuples to check
        
    Returns:
        Dictionary with health check results
    """
    results = {
        "overall_status": "healthy",
        "checks": {},
        "timestamp": time.time(),
    }
    
    # Run all checks
    checks_to_run = [
        ("cpu", lambda: check_cpu_health(cpu_threshold)),
        ("memory", lambda: check_memory_usage(memory_threshold)),
        ("disk", lambda: check_disk_usage(disk_path, disk_threshold)),
        ("load_average", lambda: check_load_average(load_threshold_multiplier)),
    ]
    
    # Add TCP checks if specified
    if tcp_checks:
        for host, port in tcp_checks:
            check_name = f"tcp_{host}_{port}"
            checks_to_run.append(
                (check_name, lambda h=host, p=port: check_tcp_port(h, p))
            )
    
    # Execute all checks
    for check_name, check_func in checks_to_run:
        try:
            status, detail, value = check_func()
            results["checks"][check_name] = {
                "status": status,
                "detail": detail,
                "value": value,
            }
            
            if status == "unhealthy":
                results["overall_status"] = "unhealthy"
                
        except Exception as e:
            results["checks"][check_name] = {
                "status": "unhealthy",
                "detail": f"Check failed: {type(e).__name__}: {str(e)}",
                "value": None,
            }
            results["overall_status"] = "unhealthy"
    
    return results


def main():
    """Main entry point for health check."""
    print("Running system health checks...")
    print("-" * 50)
    
    results = check_system_health(
        tcp_checks=[("127.0.0.1", 22)]  # Example: check SSH port
    )
    
    print(f"Overall Status: {results['overall_status'].upper()}")
    print(f"Timestamp: {time.ctime(results['timestamp'])}")
    print("-" * 50)
    
    for check_name, check_result in results["checks"].items():
        status_icon = "✓" if check_result["status"] == "healthy" else "✗"
        print(f"{status_icon} {check_name}: {check_result['detail']}")
    
    return 0 if results["overall_status"] == "healthy" else 1


if __name__ == "__main__":
    exit(main())