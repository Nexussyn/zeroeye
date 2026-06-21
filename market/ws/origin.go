package ws

import (
	"net/http"
)

// OriginChecker creates a CheckOrigin function for WebSocket upgrader.
// If allowedOrigins is empty or nil, all origins are allowed (local dev).
func OriginChecker(allowedOrigins []string) func(r *http.Request) bool {
	allowedSet := make(map[string]bool)
	for _, o := range allowedOrigins {
		allowedSet[o] = true
	}
	return func(r *http.Request) bool {
		if len(allowedSet) == 0 {
			return true // Local development: allow all
		}
		origin := r.Header.Get("Origin")
		return allowedSet[origin]
	}
}
