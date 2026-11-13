#!/bin/sh
# One-time (and safe to re-run) setup of the GitHub side of the repository: merge settings, security
# features, labels, the project board and the ruleset protecting main. What each part is for:
# docs/MAINTAINING.md. Needs the GitHub CLI signed in as the repository's owner, with the "project" scope:
#   gh auth refresh -s project
# Usage: scripts/github-setup.sh [owner/repo]   (default: this repository's GitHub remote)
set -u
repo="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
owner="${repo%%/*}"
echo "Setting up $repo"

echo "- merge settings: squash only, PR title as the commit title, delete merged branches"
gh api -X PATCH "repos/$repo" --silent \
  -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
  -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY \
  -F delete_branch_on_merge=true -F allow_update_branch=true -F has_issues=true -F has_projects=true \
  || echo "  (failed)"

echo "- security: Dependabot alerts and fixes, private vulnerability reporting"
gh api -X PUT "repos/$repo/vulnerability-alerts" --silent || echo "  (Dependabot alerts: failed)"
gh api -X PUT "repos/$repo/automated-security-fixes" --silent || echo "  (Dependabot security updates: failed)"
gh api -X PUT "repos/$repo/private-vulnerability-reporting" --silent \
  || echo "  (private vulnerability reporting: only for public repositories; run this again once it's public)"

echo "- labels"
label() { gh label create "$1" --repo "$repo" --color "$2" --description "$3" --force >/dev/null || echo "  ($1 failed)"; }
label "bug"              "d73a4a" "Something doesn't work"
label "idea"             "a2eeef" "Something Pip could do or be"
label "feature"          "0e8a16" "A new feature (pull requests)"
label "content"          "c5def5" "A blueprint or skin to share"
label "needs-triage"     "fbca04" "New: not looked at yet"
label "needs-info"       "fef2c0" "Waiting for the author; closes after 5 weeks without an answer"
label "mod"              "5319e7" "The Fabric mod (Java)"
label "brain"            "1d76db" "Her brain (Python)"
label "services"         "0052cc" "Gateway, voice, dashboard"
label "docs"             "0075ca" "Documentation"
label "ci"               "bfdadc" "CI, scripts and repository setup"
label "lan"              "006b75" "Playing with friends"
label "priority: high"   "b60205" "Soon"
label "priority: low"    "c2e0c6" "Some day"
label "good first issue" "7057ff" "A good place to start"
label "help wanted"      "008672" "Help welcome"
label "breaking"         "e11d21" "Breaks existing setups"
label "question"         "d876e3" "A question"
label "duplicate"        "cfd3d7" "Already reported"
label "wontfix"          "ffffff" "Won't be done"
label "skip-changelog"   "eeeeee" "Left out of the release notes"

echo "- project board"
num=$(gh project list --owner "$owner" --format json -q '.projects[] | select(.title=="Kindred Spirit") | .number' 2>/dev/null | head -1)
if [ -z "$num" ]; then
  num=$(gh project create --owner "$owner" --title "Kindred Spirit" --format json -q .number 2>/dev/null)
  [ -n "$num" ] && {
    gh project field-create "$num" --owner "$owner" --name "Priority" --data-type SINGLE_SELECT \
      --single-select-options "High,Medium,Low" >/dev/null
    gh project field-create "$num" --owner "$owner" --name "Area" --data-type SINGLE_SELECT \
      --single-select-options "Mod,Brain,Services,Docs,LAN,Setup" >/dev/null
  }
fi
if [ -n "$num" ]; then
  gh project link "$num" --owner "$owner" --repo "$repo" >/dev/null 2>&1
  echo "  project #$num: https://github.com/users/$owner/projects/$num"
  echo "  (in the project's Workflows, turn on 'Auto-add to project' for $repo, and add the statuses"
  echo "   Triage, To do, In progress, In review, Done to its Status field)"
else
  echo "  (failed: run 'gh auth refresh -s project' and try again)"
fi

echo "- ruleset protecting main"
if gh api "repos/$repo/rulesets" -q '.[].name' 2>/dev/null | grep -qx "Protect main"; then
  echo "  already there"
else
  gh api -X POST "repos/$repo/rulesets" --silent --input - <<'JSON' || echo "  (failed: on the free plan, rulesets need a public repository; run this again once it's public)"
{
  "name": "Protect main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 1, "require_code_owner_review": true,
      "dismiss_stale_reviews_on_push": true, "require_last_push_approval": false,
      "required_review_thread_resolution": true, "allowed_merge_methods": ["squash"]}},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [{"context": "CI passed"}]}}
  ]
}
JSON
fi
echo "Done. Also in Settings: Actions -> General -> 'Require approval for first-time contributors' (on by"
echo "default), and Discussions under Features when you want them."
