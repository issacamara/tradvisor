"""Check that an issue carries the label set required by the operating guide."""

import argparse
import json
import sys

PHASES = ("intake", "business", "ux-ui", "architect", "orchestrator",
          "implementation", "qa", "release", "operations", "defect-triage")
COMPLEXITIES = ("easy", "medium", "hard")
LANES = ("fast",)


def problems(labels):
    """Return a list of label rule violations; empty means valid."""
    found = {}
    for label in labels:
        family, _, value = label.partition(":")
        if value:
            found.setdefault(family, []).append(value)
    issues = []
    for family in ("phase", "type", "complexity"):
        values = found.get(family, [])
        if len(values) != 1:
            issues.append(f"needs exactly one {family}: label, found {len(values)}")
    if found.get("phase", [""])[0] not in PHASES and len(found.get("phase", [])) == 1:
        issues.append(f"unknown phase:{found['phase'][0]}")
    if len(found.get("complexity", [])) == 1 and found["complexity"][0] not in COMPLEXITIES:
        issues.append(f"unknown complexity:{found['complexity'][0]}")
    lanes = found.get("lane", [])
    if len(lanes) > 1 or any(lane not in LANES for lane in lanes):
        issues.append("allows at most one lane: label, and only lane:fast")
    if "fast" in lanes and found.get("complexity") != ["easy"]:
        issues.append("lane:fast requires complexity:easy")
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("event", nargs="?", help="GitHub issues event payload path")
    source.add_argument("--labels", help="Comma-separated labels to check")
    args = parser.parse_args(argv)
    if args.labels is not None:
        labels = [label.strip() for label in args.labels.split(",") if label.strip()]
    else:
        with open(args.event) as handle:
            issue = json.load(handle).get("issue", {})
        labels = [label["name"] for label in issue.get("labels", [])]
    found = problems(labels)
    for problem in found:
        print(f"Issue label rule: {problem}", file=sys.stderr)
    if not found:
        print("Issue labels satisfy the operating guide")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
