package ws

import (
	"net/http"
	"testing"
)

func TestOriginChecker_Allowed(t *testing.T) {
	checker := OriginChecker([]string{"https://example.com", "https://app.example.com"})
	req, _ := http.NewRequest("GET", "/ws", nil)
	req.Header.Set("Origin", "https://example.com")
	if !checker(req) {
		t.Error("expected origin to be allowed")
	}
}

func TestOriginChecker_Rejected(t *testing.T) {
	checker := OriginChecker([]string{"https://example.com"})
	req, _ := http.NewRequest("GET", "/ws", nil)
	req.Header.Set("Origin", "https://evil.com")
	if checker(req) {
		t.Error("expected origin to be rejected")
	}
}

func TestOriginChecker_EmptyAllowsAll(t *testing.T) {
	checker := OriginChecker(nil)
	req, _ := http.NewRequest("GET", "/ws", nil)
	req.Header.Set("Origin", "https://anything.com")
	if !checker(req) {
		t.Error("empty allowlist should allow all origins")
	}
}
