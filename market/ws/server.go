package ws

import (
	"log"
	"net/http"

	"github.com/gorilla/websocket"
	"github.com/lakhman108/zeroeye/market/config"
)

var upgrader websocket.Upgrader

// InitServer initializes the WebSocket server with configured origin checks.
func InitServer() {
	cfg := config.Load()
	upgrader = websocket.Upgrader{
		ReadBufferSize:  1024,
		WriteBufferSize: 1024,
		CheckOrigin:     OriginChecker(cfg.AllowedOrigins),
	}
}

// HandleWS handles WebSocket connections at /ws endpoint.
func HandleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("WebSocket upgrade failed: %v", err)
		return
	}
	defer conn.Close()
	// Connection handling logic here
}
