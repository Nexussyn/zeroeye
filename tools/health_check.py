# Fix for Issue #1: [0 BOUNTY] [Python] Add retry/backoff to health_check.py for transient failures

#!/usr/bin/env python3
"""
Health check module for system monitoring.
Performs health checks for CPU, memory, disk, and network with retry/backoff support.
"""

import os
import random
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, Union

# Type variables for generic decorator
F = TypeVar('F', bound=Callable[..., Any])


class HealthCheckError(Exception):
    """Custom exception for health check failures."""
    pass


class TransientError(HealthCheckError):
    """Exception for transient failures that may succeed on retry."""
    pass


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exponential_base: float = 2.0,
    jitter: bool = True
) -> Callable[[F], F]:
    """
    Decorator that implements retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        exponential_base: Base for exponential backoff (default: 2.0)
        jitter: Whether to add random jitter to delays (default: True)
    
    Returns:
        Decorated function with retry capability
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except TransientError as e:
                    last_exception = e
                    
                    # Don't sleep after the last attempt
                    if attempt < max_retries - 1:
                        # Calculate delay: 1s, 2s, 4s for base_delay=1, exponential_base=2
                        delay = base_delay * (exponential_base ** attempt)
                        
                        # Add jitter (±10%) to prevent thundering herd
                        if jitter:
                            jitter_factor = 1 + (random.random() - 0.5) * 0.2
                            delay *= jitter_factor
                        
                        time.sleep(delay)
                except Exception:
                    # Non-transient errors are raised immediately
                    raise
            
            # All retries exhausted, raise the last exception or return failure
            if last_exception:
                raise last_exception
            return None
        
        return wrapper  # type: ignore
    return decorator


def _is_transient_failure(error: Exception) -> bool:
    """
    Determine if an error is transient and worth retrying.
    
    Args:
        error: The exception to evaluate
        
    Returns:
        True if the error is likely transient, False otherwise
    """
    transient_indicators = [
        'timeout',
        'temporary',
        'unavailable',
        'connection refused',
        'network unreachable',
        'resource temporarily',
        'try again',
    ]
    
    error_msg = str(error).lower()
    return any(indicator in error_msg for indicator in transient_indicators)


@retry_with_backoff(max_retries=3, base_delay=1.0, exponential_base=2.0)
def check_cpu_health(threshold: float = 90.0) -> Dict[str, Union[str, float, bool]]:
    """
    Check CPU health status.
    
    Args:
        threshold: CPU usage percentage threshold for unhealthy status
        
    Returns:
        Dictionary containing CPU health status and metrics
        
    Raises:
        TransientError: If a transient failure occurs during check
    """
    try:
        # Read CPU stats from /proc/stat
        with open('/proc/stat', 'r') as f:
            cpu_line = f.readline()
        
        cpu_values = cpu_line.split()[1:8]
        cpu_values = [int(v) for v in cpu_values]
        
        # Calculate CPU usage
        idle = cpu_values[3]
        total = sum(cpu_values)
        
        # Get previous values if available (simplified single-point check)
        usage = 100.0 * (1 - idle / total) if total > 0 else 0.0
        
        return {
            'component': 'cpu',
            'healthy': usage < threshold,
            'usage_percent': round(usage, 2),
            'threshold': threshold,
            'message': f'CPU usage: {usage:.2f}%'
        }
        
    except FileNotFoundError:
        # Fallback for non-Linux systems
        return {
            'component': 'cpu',
            'healthy': True,
            'usage_percent': 0.0,
            'threshold': threshold,
            'message': 'CPU check not available on this platform'
        }
    except (IOError, OSError) as e:
        if _is_transient_failure(e):
            raise TransientError(f'Transient CPU check failure: {e}')
        raise


@retry_with_backoff(max_retries=3, base_delay=1.0, exponential_base=2.0)
def check_memory_health(threshold: float = 90.0) -> Dict[str, Union[str, float, bool]]:
    """
    Check memory health status.
    
    Args:
        threshold: Memory usage percentage threshold for unhealthy status
        
    Returns:
        Dictionary containing memory health status and metrics
        
    Raises:
        TransientError: If a transient failure occurs during check
    """
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = {}
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split()[0]
                    meminfo[key] = int(value)
        
        total = meminfo.get('MemTotal', 1)
        available = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
        
        usage = 100.0 * (1 - available / total) if total > 0 else 0.0
        
        return {
            'component': 'memory',
            'healthy': usage < threshold,
            'usage_percent': round(usage, 2),
            'total_kb': total,
            'available_kb': available,
            'threshold': threshold,
            'message': f'Memory usage: {usage:.2f}%'
        }
        
    except FileNotFoundError:
        # Fallback for non-Linux systems
        return {
            'component': 'memory',
            'healthy': True,
            'usage_percent': 0.0,
            'total_kb': 0,
            'available_kb': 0,
            'threshold': threshold,
            'message': 'Memory check not available on this platform'
        }
    except (IOError, OSError) as e:
        if _is_transient_failure(e):
            raise TransientError(f'Transient memory check failure: {e}')
        raise


@retry_with_backoff(max_retries=3, base_delay=1.0, exponential_base=2.0)
def check_disk_health(
    path: str = '/',
    threshold: float = 90.0
) -> Dict[str, Union[str, float, bool, int]]:
    """
    Check disk health status.
    
    Args:
        path: Filesystem path to check
        threshold: Disk usage percentage threshold for unhealthy status
        
    Returns:
        Dictionary containing disk health status and metrics
        
    Raises:
        TransientError: If a transient failure occurs during check
    """
    try:
        stat = os.statvfs(path)
        
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        used = total - free
        
        usage = 100.0 * (used / total) if total > 0 else 0.0
        
        return {
            'component': 'disk',
            'healthy': usage < threshold,
            'path': path,
            'usage_percent': round(usage, 2),
            'total_bytes': total,
            'free_bytes': free,
            'used_bytes': used,
            'threshold': threshold,
            'message': f'Disk usage at {path}: {usage:.2f}%'
        }
        
    except (IOError, OSError) as e:
        if _is_transient_failure(e):
            raise TransientError(f'Transient disk check failure: {e}')
        raise


@retry_with_backoff(max_retries=3, base_delay=1.0, exponential_base=2.0)
def check_network_health(
    timeout: float = 5.0
) -> Dict[str, Union[str, bool]]:
    """
    Check network health status by verifying basic connectivity.
    
    Args:
        timeout: Timeout in seconds for network check
        
    Returns:
        Dictionary containing network health status
        
    Raises:
        TransientError: If a transient failure occurs during check
    """
    import socket
    
    try:
        # Try to resolve a well-known hostname
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname('dns.google')
        
        return {
            'component': 'network',
            'healthy': True,
            'message': 'Network connectivity OK'
        }
        
    except socket.timeout:
        raise TransientError('Network check timeout - transient failure')
    except socket.gaierror as e:
        error_msg = str(e).lower()
        if 'temporary' in error_msg or 'try again' in error_msg:
            raise TransientError(f'Transient DNS failure: {e}')
        return {
            'component': 'network',
            'healthy': False,
            'message': f'Network check failed: {e}'
        }
    except OSError as e:
        if _is_transient_failure(e):
            raise TransientError(f'Transient network failure: {e}')
        return {
            'component': 'network',
            'healthy': False,
            'message': f'Network check failed: {e}'
        }


def check_system_health(
    cpu_threshold: float = 90.0,
    memory_threshold: float = 90.0,
    disk_threshold: float = 90.0,
    disk_path: str = '/',
    network_timeout: float = 5.0
) -> Dict[str, Any]:
    """
    Perform comprehensive system health check.
    
    Orchestrates all individual health checks with retry/backoff support.
    Each check independently retries up to 3 times with exponential backoff.
    
    Args:
        cpu_threshold: CPU usage threshold percentage
        memory_threshold: Memory usage threshold percentage
        disk_threshold: Disk usage threshold percentage
        disk_path: Path to check for disk usage
        network_timeout: Timeout for network connectivity check
        
    Returns:
        Dictionary containing overall health status and individual check results
    """
    results: Dict[str, Any] = {
        'timestamp': time.time(),
        'overall_healthy': True,
        'checks': {}
    }
    
    # Run all health checks, each with their own retry logic
    checks = [
        ('cpu', lambda: check_cpu_health(threshold=cpu_threshold)),
        ('memory', lambda: check_memory_health(threshold=memory_threshold)),
        ('disk', lambda: check_disk_health(path=disk_path, threshold=disk_threshold)),
        ('network', lambda: check_network_health(timeout=network_timeout)),
    ]
    
    for check_name, check_func in checks:
        try:
            check_result = check_func()
            results['checks'][check_name] = check_result
            
            # Update overall health status
            if not check_result.get('healthy', False):
                results['overall_healthy'] = False
                
        except TransientError as e:
            # All retries exhausted for this check
            results['checks'][check_name] = {
                'component': check_name,
                'healthy': False,
                'message': f'Check failed after retries: {e}',
                'error': str(e)
            }
            results['overall_healthy'] = False
            
        except Exception as e:
            # Non-transient error
            results['checks'][check_name] = {
                'component': check_name,
                'healthy': False,
                'message': f'Check failed: {e}',
                'error': str(e)
            }
            results['overall_healthy'] = False
    
    return results


def main() -> None:
    """Main entry point for health check module."""
    import json
    
    print("Running system health checks...")
    results = check_system_health()
    
    print(json.dumps(results, indent=2))
    
    if results['overall_healthy']:
        print("\n✓ All health checks passed")
    else:
        print("\n✗ Some health checks failed")
        exit(1)


if __name__ == '__main__':
    main()