package main

import (
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// loadPrivateKey reads a PEM-encoded RSA private key from disk.
func loadPrivateKey(path string) (*rsa.PrivateKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading private key: %w", err)
	}

	block, _ := pem.Decode(data)
	if block == nil {
		return nil, fmt.Errorf("no PEM block found in %s", path)
	}

	// Try PKCS1 first, then PKCS8.
	if key, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return key, nil
	}

	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parsing private key: %w", err)
	}

	key, ok := parsed.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("private key is not RSA")
	}
	return key, nil
}

// createJWT creates a short-lived JWT for GitHub App authentication.
func createJWT(appID int64, key *rsa.PrivateKey) (string, error) {
	now := time.Now()
	claims := jwt.RegisteredClaims{
		IssuedAt:  jwt.NewNumericDate(now.Add(-60 * time.Second)),
		ExpiresAt: jwt.NewNumericDate(now.Add(10 * time.Minute)),
		Issuer:    strconv.FormatInt(appID, 10),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)
	return token.SignedString(key)
}

type installation struct {
	ID int64 `json:"id"`
}

type accessTokenResponse struct {
	Token     string `json:"token"`
	ExpiresAt string `json:"expires_at"`
}

// getInstallationToken generates an ephemeral GitHub App installation token.
func getInstallationToken(appID int64, key *rsa.PrivateKey) (string, string, error) {
	jwtToken, err := createJWT(appID, key)
	if err != nil {
		return "", "", fmt.Errorf("creating JWT: %w", err)
	}

	client := &http.Client{Timeout: 30 * time.Second}

	// Get installations.
	req, err := http.NewRequest("GET", "https://api.github.com/app/installations", nil)
	if err != nil {
		return "", "", err
	}
	req.Header.Set("Authorization", "Bearer "+jwtToken)
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := client.Do(req)
	if err != nil {
		return "", "", fmt.Errorf("listing installations: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return "", "", fmt.Errorf("list installations returned %d: %s", resp.StatusCode, body)
	}

	var installations []installation
	if err := json.NewDecoder(resp.Body).Decode(&installations); err != nil {
		return "", "", fmt.Errorf("decoding installations: %w", err)
	}
	if len(installations) == 0 {
		return "", "", fmt.Errorf("no installations found for app %d", appID)
	}

	instID := installations[0].ID

	// Create access token.
	tokenURL := fmt.Sprintf("https://api.github.com/app/installations/%d/access_tokens", instID)
	req, err = http.NewRequest("POST", tokenURL, nil)
	if err != nil {
		return "", "", err
	}
	req.Header.Set("Authorization", "Bearer "+jwtToken)
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err = client.Do(req)
	if err != nil {
		return "", "", fmt.Errorf("creating access token: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		return "", "", fmt.Errorf("create access token returned %d: %s", resp.StatusCode, body)
	}

	var tokenResp accessTokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
		return "", "", fmt.Errorf("decoding access token: %w", err)
	}

	return tokenResp.Token, tokenResp.ExpiresAt, nil
}
