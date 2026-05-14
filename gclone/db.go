package main

import (
	"database/sql"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

func nowUnix() int64 {
	return time.Now().Unix()
}

func openDB() (*sql.DB, error) {
	dir := os.Getenv("HOME") + "/.local/share/gclone"
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, err
	}
	dbPath := filepath.Join(dir, "gclone.db")
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, err
	}
	if _, err := db.Exec(createSchema); err != nil {
		return nil, err
	}
	return db, nil
}

const createSchema = `
CREATE TABLE IF NOT EXISTS urls (
    url         TEXT PRIMARY KEY,
    score       REAL NOT NULL DEFAULT 1.0,
    last_access INTEGER NOT NULL
);
`

func bump(db *sql.DB, url string) {
	now := nowUnix()
	db.Exec("INSERT INTO urls (url, score, last_access) VALUES (?, 1.0, ?) ON CONFLICT(url) DO UPDATE SET score = score + 1.0 / (CAST(? AS REAL) - last_access + 1.0), last_access = ?", url, now, now, now)
}

func query(db *sql.DB, term string) (string, error) {
	rows, err := db.Query("SELECT url, score FROM urls")
	if err != nil {
		return "", err
	}
	defer rows.Close()

	var bestURL string
	var bestScore float64
	for rows.Next() {
		var url string
		var score float64
		rows.Scan(&url, &score)
		lurl := strings.ToLower(url)
		lterm := strings.ToLower(term)
		if strings.Contains(lurl, lterm) && score > bestScore {
			bestURL = url
			bestScore = score
		}
	}
	if bestURL == "" {
		return "", errors.New("no match")
	}
	return bestURL, nil
}

