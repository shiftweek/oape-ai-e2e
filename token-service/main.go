package main

import (
	"crypto/rsa"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
)

type tokenResponse struct {
	Token     string `json:"token"`
	ExpiresAt string `json:"expires_at"`
}

type errorResponse struct {
	Error string `json:"error"`
}

func main() {
	appIDStr := os.Getenv("GITHUB_APP_ID")
	if appIDStr == "" {
		log.Fatal("GITHUB_APP_ID environment variable is required")
	}
	appID, err := strconv.ParseInt(appIDStr, 10, 64)
	if err != nil {
		log.Fatalf("invalid GITHUB_APP_ID: %v", err)
	}

	keyPath := os.Getenv("GITHUB_APP_PRIVATE_KEY_PATH")
	if keyPath == "" {
		keyPath = "/secrets/github-app/private-key.pem"
	}

	privateKey, err := loadPrivateKey(keyPath)
	if err != nil {
		log.Fatalf("failed to load private key: %v", err)
	}
	log.Printf("Loaded GitHub App private key from %s", keyPath)

	listenAddr := os.Getenv("LISTEN_ADDR")
	if listenAddr == "" {
		listenAddr = ":8081"
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /token", handleToken(appID, privateKey))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})

	log.Printf("Token service listening on %s", listenAddr)
	log.Fatal(http.ListenAndServe(listenAddr, mux))
}

func handleToken(appID int64, key *rsa.PrivateKey) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		token, expiresAt, err := getInstallationToken(appID, key)
		if err != nil {
			log.Printf("ERROR: generating token: %v", err)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(errorResponse{Error: err.Error()})
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(tokenResponse{
			Token:     token,
			ExpiresAt: expiresAt,
		})
	}
}
