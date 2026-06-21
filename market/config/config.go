package config

import (
	"os"
	"strings"
)

type Config struct {
	AllowedOrigins []string
}

func Load() *Config {
	origins := os.Getenv("WS_ALLOWED_ORIGINS")
	if origins == "" {
		return &Config{AllowedOrigins: nil}
	}
	parts := strings.Split(origins, ",")
	var allowed []string
	for _, p := range parts {
		trimmed := strings.TrimSpace(p)
		if trimmed != "" {
			allowed = append(allowed, trimmed)
		}
	}
	return &Config{AllowedOrigins: allowed}
}
