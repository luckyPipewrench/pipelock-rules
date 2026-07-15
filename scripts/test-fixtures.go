// Command test-fixtures runs bundle fixtures with Go's regexp package, the
// same RE2 implementation used by Pipelock in production.
package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

const maxFixtureLineBytes = 1 << 20

var (
	idLine        = regexp.MustCompile(`^\s*- id:\s*(\S+)\s*$`)
	statusLine    = regexp.MustCompile(`^\s*status:\s*(\S+)\s*$`)
	regexLine     = regexp.MustCompile(`^\s*regex:\s*'(.*)'\s*$`)
	validatorLine = regexp.MustCompile(`^\s*validator:\s*(\S+)\s*$`)
)

type rule struct {
	id        string
	status    string
	pattern   string
	validator string
}

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: go run ./scripts/test-fixtures.go BUNDLE_FILE FIXTURE_ROOT")
		os.Exit(2)
	}
	rules, err := parseRules(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "ERROR: %v\n", err)
		os.Exit(1)
	}
	passes, failures := testRules(rules, os.Args[2])
	failures = append(failures, findOrphanFixtures(rules, os.Args[2])...)
	sort.Strings(failures)
	for _, failure := range failures {
		fmt.Printf("FAIL: %s\n", failure)
	}
	fmt.Printf("\nResults: %d passed, %d failed, 0 skipped\n", passes, len(failures))
	if len(failures) != 0 {
		os.Exit(1)
	}
}

func parseRules(path string) ([]rule, error) {
	// compile.sh emits a canonical, single-line subset for these fields. Keep
	// this parser strict and fail closed if that compiler contract changes.
	file, err := os.Open(filepath.Clean(path))
	if err != nil {
		return nil, fmt.Errorf("open bundle: %w", err)
	}
	defer func() { _ = file.Close() }()
	var rules []rule
	var current *rule
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), maxFixtureLineBytes)
	for scanner.Scan() {
		line := scanner.Text()
		if match := idLine.FindStringSubmatch(line); match != nil {
			if current != nil {
				if err := validateParsedRule(current); err != nil {
					return nil, err
				}
				rules = append(rules, *current)
			}
			current = &rule{id: match[1]}
			continue
		}
		if current == nil {
			continue
		}
		if match := statusLine.FindStringSubmatch(line); match != nil {
			current.status = match[1]
			continue
		}
		if match := validatorLine.FindStringSubmatch(line); match != nil {
			current.validator = match[1]
			continue
		}
		if match := regexLine.FindStringSubmatch(line); match != nil {
			current.pattern = strings.ReplaceAll(match[1], "''", "'")
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read bundle: %w", err)
	}
	if current != nil {
		if err := validateParsedRule(current); err != nil {
			return nil, err
		}
		rules = append(rules, *current)
	}
	if len(rules) == 0 {
		return nil, fmt.Errorf("bundle contains no parsed rules")
	}
	return rules, nil
}

func validateParsedRule(current *rule) error {
	if current.status != "stable" && current.status != "experimental" {
		return fmt.Errorf("rule %s has missing or unsupported status %q", current.id, current.status)
	}
	if current.pattern == "" {
		return fmt.Errorf("rule %s has no regex", current.id)
	}
	return nil
}

func testRules(rules []rule, fixtureRoot string) (int, []string) {
	passes := 0
	var failures []string
	for _, rule := range rules {
		compiled, err := regexp.Compile("(?i)" + rule.pattern)
		if err != nil {
			failures = append(failures, fmt.Sprintf("%s bad RE2 regex: %v", rule.id, err))
			continue
		}
		ruleType, tpPath, fpPath := fixturePaths(fixtureRoot, rule.id)
		if ruleType == "" {
			failures = append(failures, fmt.Sprintf("%s has no true-positive fixture", rule.id))
			continue
		}
		if rule.validator != "" && rule.validator != "aba" {
			failures = append(failures, fmt.Sprintf("%s fixture runner does not support validator %q", rule.id, rule.validator))
			continue
		}
		count, errs := testFixtureFile(rule.id, tpPath, compiled, rule.validator, true)
		passes += count
		failures = append(failures, errs...)
		if _, err := os.Stat(fpPath); err == nil {
			count, errs = testFixtureFile(rule.id, fpPath, compiled, rule.validator, false)
			passes += count
			failures = append(failures, errs...)
		} else if rule.status == "stable" {
			failures = append(failures, fmt.Sprintf("%s stable rule has no false-positive fixture", rule.id))
		}
	}
	return passes, failures
}

func fixturePaths(root, id string) (string, string, string) {
	for _, ruleType := range []string{"dlp", "injection", "tool-poison"} {
		tp := filepath.Join(root, ruleType, id+"-true-positive.txt")
		fp := filepath.Join(root, ruleType, id+"-false-positive.txt")
		if _, err := os.Stat(tp); err == nil {
			return ruleType, tp, fp
		}
	}
	return "", "", ""
}

func testFixtureFile(id, path string, compiled *regexp.Regexp, validator string, wantMatch bool) (int, []string) {
	file, err := os.Open(filepath.Clean(path))
	if err != nil {
		return 0, []string{fmt.Sprintf("%s open fixture %s: %v", id, path, err)}
	}
	defer func() { _ = file.Close() }()
	passes := 0
	var failures []string
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 64*1024), maxFixtureLineBytes)
	lineNumber := 0
	for scanner.Scan() {
		lineNumber++
		line := scanner.Text()
		if strings.TrimSpace(line) == "" {
			continue
		}
		matched := effectiveMatch(compiled, validator, line)
		if matched == wantMatch {
			passes++
			continue
		}
		kind := "true-positive did not match"
		if !wantMatch {
			kind = "false-positive matched"
		}
		failures = append(failures, fmt.Sprintf("%s %s:%d: %s: %s", id, path, lineNumber, kind, line))
	}
	if err := scanner.Err(); err != nil {
		failures = append(failures, fmt.Sprintf("%s read fixture %s: %v", id, path, err))
	}
	return passes, failures
}

func effectiveMatch(compiled *regexp.Regexp, validator, input string) bool {
	for _, match := range compiled.FindAllString(input, -1) {
		if validator == "" || (validator == "aba" && validateABA(match)) {
			return true
		}
	}
	return false
}

func validateABA(input string) bool {
	digits := make([]byte, 0, 9)
	for i := range len(input) {
		if input[i] >= '0' && input[i] <= '9' {
			digits = append(digits, input[i]-'0')
		}
	}
	if len(digits) != 9 {
		return false
	}
	sum := 3*int(digits[0]+digits[3]+digits[6]) + 7*int(digits[1]+digits[4]+digits[7]) + int(digits[2]+digits[5]+digits[8])
	return sum%10 == 0
}

func findOrphanFixtures(rules []rule, root string) []string {
	known := make(map[string]struct{}, len(rules))
	for _, rule := range rules {
		known[rule.id] = struct{}{}
	}
	var failures []string
	err := filepath.WalkDir(root, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".txt") {
			return nil
		}
		id := strings.TrimSuffix(entry.Name(), "-true-positive.txt")
		if id == entry.Name() {
			id = strings.TrimSuffix(entry.Name(), "-false-positive.txt")
		}
		if id == entry.Name() {
			failures = append(failures, fmt.Sprintf("unrecognized fixture filename %s", path))
		} else if _, ok := known[id]; !ok {
			failures = append(failures, fmt.Sprintf("orphan fixture %s has no bundle rule", path))
		}
		return nil
	})
	if err != nil {
		failures = append(failures, fmt.Sprintf("walk fixtures: %v", err))
	}
	return failures
}
