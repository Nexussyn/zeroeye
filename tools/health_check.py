# Fix for Issue #1: [0 BOUNTY] [Python] Add retry/backoff to health_check.py for transient failures

"""
Health check module for system monitoring.
Performs health checks for CPU, memory, disk, and network with retry/backoff support.
"""

import time
import random
import psutil
import socket
from typing import Dict, Any, Callable, TypeVar, Optional
from functools import wraps

T = TypeVar('T')

# Retry configuration
MAX_RETRIES: int = 3
BASE_DELAY: float = 1.0  # Base delay in seconds
MAX_JITTER: float = 0.1  # Maximum jitter factor (10%)


class TransientError(Exception):
    """Exception representing a transient/recoverable failure."""
    pass


def retry_with_backoff(
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    transient_exceptions: tuple = (TransientError, TimeoutError, ConnectionError, OSError)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that implements retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        transient_exceptions: Tuple of exception types considered transient
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except transient_exceptions as e:
                    last_exception = e
                    
                    # Don't sleep after the last attempt
                    if attempt < max_retries - 1:
                        # Calculate exponential backoff: 1s, 2s, 4s
                        delay = base_delay * (2 ** attempt)
                        # Add small random jitter to prevent thundering herd
                        jitter = delay * random.uniform(0, MAX_JITTER)
                        time.sleep(delay + jitter)
            
            # All retries exhausted - return failure result based on function
            # Return a failure dict that matches expected health check format
            return {
                "status": "unhealthy",
                "error": f"Failed after {max_retries} retries: {str(last_exception)}",
                "retries_exhausted": True
            }
        
        return wrapper
    return decorator


@retry_with_backoff()
def check_cpu_health(threshold: float = 90.0) -> Dict[str, Any]:
    """
    Check CPU health status.
    
    Args:
        threshold: CPU usage percentage threshold for unhealthy status
    
    Returns:
        Dict containing CPU health status and metrics
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Treat extremely high readings during brief spikes as potentially transient
        if cpu_percent >= 99.9:
            raise TransientError("CPU reading at maximum, possible transient spike")
        
        status = "healthy" if cpu_percent < threshold else "unhealthy"
        
        return {
            "status": status,
            "cpu_percent": cpu_percent,
            "threshold": threshold
        }
    except psutil.Error as e:
        # psutil errors may be transient (e.g., during system stress)
        raise TransientError(f"psutil error: {e}") from e


@retry_with_backoff()
def check_memory_health(threshold: float = 90.0) -> Dict[str, Any]:
    """
    Check memory health status.
    
    Args:
        threshold: Memory usage percentage threshold for unhealthy status
    
    Returns:
        Dict containing memory health status and metrics
    """
    try:
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        status = "healthy" if memory_percent < threshold else "unhealthy"
        
        return {
            "status": status,
            "memory_percent": memory_percent,
            "memory_available_gb": round(memory.available / (1024 ** 3), 2),
            "memory_total_gb": round(memory.total / (1024 ** 3), 2),
            "threshold": threshold
        }
    except psutil.Error as e:
        raise TransientError(f"psutil error: {e}") from e


@retry_with_backoff()
def check_disk_health(path: str = "/", threshold: float = 90.0) -> Dict[str, Any]:
    """
    Check disk health status.
    
    Args:
        path: Filesystem path to check
        threshold: Disk usage percentage threshold for unhealthy status
    
    Returns:
        Dict containing disk health status and metrics
    """
    try:
        disk = psutil.disk_usage(path)
        disk_percent = disk.percent
        
        status = "healthy" if disk_percent < threshold else "unhealthy"
        
        return {
            "status": status,
            "disk_percent": disk_percent,
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
            "path": path,
            "threshold": threshold
        }
    except (psutil.Error, FileNotFoundError, PermissionError) as e:
        raise TransientError(f"Disk check error: {e}") from e


@retry_with_backoff()
def check_network_health(
    host: str = "8.8.8.8",
    port: int = 53,
    timeout: float = 3.0
) -> Dict[str, Any]:
    """
    Check network connectivity health status.
    
    Args:
        host: Host to check connectivity against
        port: Port to connect to
        timeout: Connection timeout in seconds
    
    Returns:
        Dict containing network health status and metrics
    """
    start_time = time.time()
    
    try:
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
        
        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        return {
            "status": "healthy",
            "host": host,
            "port": port,
            "latency_ms": latency_ms
        }
    except socket.timeout as e:
        raise TimeoutError(f"Connection to {host}:{port} timed out") from e
    except socket.error as e:
        raise ConnectionError(f"Network error connecting to {host}:{port}: {e}") from e


def check_system_health(
    cpu_threshold: float = 90.0,
    memory_threshold: float = 90.0,
    disk_threshold: float = 90.0,
    disk_path: str = "/",
    network_host: str = "8.8.8.8",
    network_port: int = 53,
    network_timeout: float = 3.0
) -> Dict[str, Any]:
    """
    Perform comprehensive system health check.
    
    Orchestrates all individual health checks and aggregates results.
    Each sub-check has its own retry logic with exponential backoff.
    
    Args:
        cpu_threshold: CPU usage threshold percentage
        memory_threshold: Memory usage threshold percentage
        disk_threshold: Disk usage threshold percentage
        disk_path: Filesystem path for disk check
        network_host: Host for network connectivity check
        network_port: Port for network connectivity check
        network_timeout: Timeout for network check
    
    Returns:
        Dict containing overall health status and individual check results
    """
    results: Dict[str, Any] = {
        "timestamp": time.time(),
        "checks": {}
    }
    
    # Run all health checks (each has its own retry logic)
    results["checks"]["cpu"] = check_cpu_health(threshold=cpu_threshold)
    results["checks"]["memory"] = check_memory_health(threshold=memory_threshold)
    results["checks"]["disk"] = check_disk_health(path=disk_path, threshold=disk_threshold)
    results["checks"]["network"] = check_network_health(
        host=network_host,
        port=network_port,
        timeout=network_timeout
    )
    
    # Determine overall health status
    all_healthy = all(
        check.get("status") == "healthy"
        for check in results["checks"].values()
    )
    
    results["overall_status"] = "healthy" if all_healthy else "unhealthy"
    
    # Count any checks that exhausted retries
    retry_failures = sum(
        1 for check in results["checks"].values()
        if check.get("retries_exhausted", False)
    )
    
    if retry_failures > 0:
        results["retry_failures"] = retry_failures
    
    return results


def get_health_summary() -> str:
    """
    Get a human-readable health summary.
    
    Returns:
        String summary of system health status
    """
    health = check_system_health()
    
    lines = [
        f"System Health: {health['overall_status'].upper()}",
        "-" * 40
    ]
    
    for name, check in health["checks"].items():
        status = check.get("status", "unknown")
        status_icon = "✓" if status == "healthy" else "✗"
        
        if check.get("retries_exhausted"):
            status_icon = "⚠"
            
        lines.append(f"  {status_icon} {name.capitalize()}: {status}")
        
        # Add relevant metrics
        if "cpu_percent" in check:
            lines.append(f"      Usage: {check['cpu_percent']}%")
        if "memory_percent" in check:
            lines.append(f"      Usage: {check['memory_percent']}%")
        if "disk_percent" in check:
            lines.append(f"      Usage: {check['disk_percent']}%")
        if "latency_ms" in check:
            lines.append(f"      Latency: {check['latency_ms']}ms")
        if "error" in check:
            lines.append(f"      Error: {check['error']}")
    
    if health.get("retry_failures"):
        lines.append("-" * 40)
        lines.append(f"Warning: {health['retry_failures']} check(s) failed after retries")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print(get_health_summary())