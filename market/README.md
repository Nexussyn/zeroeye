# Market WebSocket Server

## Configuration

### WebSocket Origin Validation

Set the `WS_ALLOWED_ORIGINS` environment variable to a comma-separated list of allowed origins.

```bash
# Production
export WS_ALLOWED_ORIGINS="https://example.com,https://app.example.com"
```

### Local Development

When `WS_ALLOWED_ORIGINS` is not set or empty, all origins are allowed. This is intended for local development convenience.

**Warning:** Always set `WS_ALLOWED_ORIGINS` in production environments.
