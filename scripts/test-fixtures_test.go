package main

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func TestProductionRE2UnicodeWordSemantics(t *testing.T) {
	compiled := regexp.MustCompile(`(?i)^\w+$`)
	if compiled.MatchString("секрет") {
		t.Fatal("Go RE2 unexpectedly treated Unicode letters as \\w; fixture runner must preserve production semantics")
	}
}

func TestStableRuleRequiresFalsePositiveFixture(t *testing.T) {
	root := t.TempDir()
	tp := filepath.Join(root, "dlp", "dlp-example-true-positive.txt")
	if err := os.MkdirAll(filepath.Dir(tp), 0o750); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}
	if err := os.WriteFile(tp, []byte("token_example\n"), 0o600); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}
	passes, failures := testRules([]rule{{id: "dlp-example", status: "stable", pattern: `token_\w+`}}, root)
	if passes != 1 {
		t.Fatalf("passes = %d, want 1", passes)
	}
	if len(failures) != 1 || !strings.Contains(failures[0], "no false-positive fixture") {
		t.Fatalf("failures = %v", failures)
	}
}

func TestEveryRuleRequiresTruePositiveFixture(t *testing.T) {
	passes, failures := testRules([]rule{{id: "injection-example", status: "experimental", pattern: `ignore`}}, t.TempDir())
	if passes != 0 || len(failures) != 1 || !strings.Contains(failures[0], "no true-positive fixture") {
		t.Fatalf("passes=%d failures=%v", passes, failures)
	}
}

func TestABAValidatorMatchesProductionChecksum(t *testing.T) {
	compiled := regexp.MustCompile(`(?i)\b(?:routing|aba)[\s:=]+\d{9}\b`)
	if !effectiveMatch(compiled, "aba", "routing: 011000015") {
		t.Fatal("valid ABA routing number rejected")
	}
	if effectiveMatch(compiled, "aba", "routing: 123456789") {
		t.Fatal("invalid ABA routing checksum accepted")
	}
}

func TestParseRulesRejectsMissingStatus(t *testing.T) {
	bundle := filepath.Join(t.TempDir(), "bundle.yaml")
	content := "rules:\n  - id: injection-example\n    pattern:\n      regex: 'ignore'\n"
	if err := os.WriteFile(bundle, []byte(content), 0o600); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}
	_, err := parseRules(bundle)
	if err == nil || !strings.Contains(err.Error(), "missing or unsupported status") {
		t.Fatalf("parseRules error = %v", err)
	}
}
