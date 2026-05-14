package main

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

func main() {
	if len(os.Args) == 2 && (os.Args[1] == "-h" || os.Args[1] == "--help") {
		fmt.Println("usage: gclone <url | term> [dest]")
		os.Exit(0)
	}
	if len(os.Args) < 2 {
		die("usage: gclone <url | term> [dest]")
	}
	arg := os.Args[1]
	dest := ""
	if len(os.Args) >= 3 {
		dest = os.Args[2]
	}

	db, err := openDB()
	if err != nil {
		die("failed to open db: %v", err)
	}
	defer db.Close()

	if looksLikeURL(arg) || looksLikePath(arg) {
		runClone(arg, dest)
		bump(db, arg)
		return
	}

	url, err := query(db, arg)
	if err != nil {
		die("no match for %q", arg)
	}
	fmt.Printf("→ %s\n", url)
	runClone(url, dest)
	bump(db, url)
}

func runClone(url string, dest string) {
	cmd := exec.Command("git", "clone", url)
	if dest != "" {
		cmd.Args = append(cmd.Args, dest)
	}
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.WaitDelay = 60 * time.Second
	if err := cmd.Run(); err != nil {
		die("clone failed")
	}
}

func looksLikeURL(s string) bool {
	return strings.Contains(s, "://") || strings.HasPrefix(s, "git@")
}

func looksLikePath(s string) bool {
	return strings.HasPrefix(s, "/") || strings.HasPrefix(s, ".") || strings.Contains(s, ":")
}

func die(format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}