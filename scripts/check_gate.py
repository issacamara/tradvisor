"""Check that a human decision approves the current head of a pull request.

Run immediately before merging. Exit 0 means the latest decision for the
current head approves it without conditions; exit 1 leaves the step pending.
"""

import argparse
import json
import re
import subprocess
import sys

GATES = {"merge": "merge", "production": "production promotion"}
FIELD = re.compile(r"^\s*-\s*\*\*(?P<key>[^*]+)\*\*\s*[—-]+\s*(?P<value>.*?)\s*$", re.MULTILINE)
NO_CONDITIONS = {"", "none", "n/a"}


def parse_decision(body):
    """Return the human-decision fields of a comment body, or None."""
    fields = {m["key"].strip().lower(): m["value"] for m in FIELD.finditer(body or "")}
    if "gate" not in fields or "decision" not in fields:
        return None
    return fields


def evaluate(head, comments, reviews, gate="merge", approvers=()):
    """Return (approved, reason) for the latest decision on this head."""
    wanted = GATES[gate]
    allowed = {login.lower() for login in approvers}
    events = []
    for comment in comments:
        author = (comment.get("author") or {}).get("login", "")
        fields = parse_decision(comment.get("body"))
        if not fields or fields["gate"].strip().lower() != wanted:
            continue
        if head not in fields.get("approved item", ""):
            continue
        if allowed and author.lower() not in allowed:
            continue
        decision = fields["decision"].strip().lower()
        conditions = fields.get("conditions", "").strip().lower()
        events.append((comment.get("createdAt", ""), author, decision, conditions))
    if gate == "merge":
        for review in reviews:
            author = (review.get("author") or {}).get("login", "")
            if (review.get("commit") or {}).get("oid") != head:
                continue
            if allowed and author.lower() not in allowed:
                continue
            state = review.get("state", "")
            if state in ("APPROVED", "CHANGES_REQUESTED"):
                decision = "approved" if state == "APPROVED" else "changes requested"
                events.append((review.get("submittedAt", ""), author, decision, ""))
    if not events:
        return False, f"No {wanted} decision references head {head}"
    _, author, decision, conditions = max(events, key=lambda event: event[0])
    if decision != "approved":
        return False, f"Latest decision by {author} on {head} is '{decision}'"
    if conditions not in NO_CONDITIONS:
        return False, f"Approval by {author} has open conditions: {conditions}"
    return True, f"Head {head} approved by {author} for {wanted}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", help="Pull request number or URL")
    parser.add_argument("--repo", help="OWNER/NAME when not run inside the repository")
    parser.add_argument("--gate", choices=tuple(GATES), default="merge")
    parser.add_argument("--approver", action="append", default=[],
                        help="GitHub login whose decisions count; repeat for several")
    args = parser.parse_args(argv)
    command = ["gh", "pr", "view", args.pr, "--json", "headRefOid,comments,reviews"]
    if args.repo:
        command += ["--repo", args.repo]
    try:
        data = json.loads(subprocess.check_output(command, text=True))
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"Gate check failed to read the pull request: {error}", file=sys.stderr)
        return 2
    approved, reason = evaluate(data["headRefOid"], data.get("comments", []),
                                data.get("reviews", []), args.gate, args.approver)
    print(reason, file=sys.stdout if approved else sys.stderr)
    return 0 if approved else 1


if __name__ == "__main__":
    sys.exit(main())
