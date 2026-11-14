#!/bin/bash
# Kindred Spirit's Modrinth project, managed from here. The token is read from the macOS Keychain (service
# "kindred-modrinth"), never from a file or the command line, and never printed. It should only allow projects and
# versions (create, read, write): nothing about money, the account, or deleting.
#   scripts/modrinth.sh create        create the project as a private draft (only its members see it) from
#                                     docs/modrinth.md, and set MODRINTH_PROJECT_ID in GitHub for the release workflow
#   scripts/modrinth.sh update-page   replace the draft's page text with docs/modrinth.md
#   scripts/modrinth.sh show          the project's status, as Modrinth has it
# Making it visible to others (submitting it for review, listing it) is done on modrinth.com by its owner.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="https://api.modrinth.com/v2"
UA="kindred-spirit-scripts (github.com/PetitPotam/kindred-spirit)"
REPO="PetitPotam/kindred-spirit"

token() { security find-generic-password -s kindred-modrinth -w 2>/dev/null || { echo "No token in the Keychain (kindred-modrinth)." >&2; exit 1; }; }
project_id() { gh variable get MODRINTH_PROJECT_ID -R "$REPO" 2>/dev/null || true; }

case "${1:-}" in
  create)
    [[ -n "$(project_id)" ]] && { echo "Already created: $(project_id)"; exit 0; }
    data=$(python3 - "$ROOT/docs/modrinth.md" <<'PY'
import json, sys
body = open(sys.argv[1]).read().split("\n", 2)[2].strip()  # (the page, without its title line)
print(json.dumps({
    "slug": "kindred-spirit", "title": "Kindred Spirit", "project_type": "mod",
    "description": "Pip, a little AI companion who talks with you by voice, helps, builds, remembers, and has feelings.",
    "body": body, "categories": ["utility", "social", "adventure"], "additional_categories": [],
    "client_side": "required", "server_side": "unsupported", "license_id": "AGPL-3.0-only",
    "source_url": "https://github.com/PetitPotam/kindred-spirit",
    "issues_url": "https://github.com/PetitPotam/kindred-spirit/issues",
    "wiki_url": "https://kindred-spirit-pip.web.app",
    "initial_versions": [], "is_draft": True, "requested_status": "private"}))
PY
)
    out=$(curl -sS -X POST "$API/project" -H "Authorization: $(token)" -H "User-Agent: $UA" \
      --form-string "data=$data" -F "icon=@$ROOT/mod/src/main/resources/assets/kindredspirit/icon.png;type=image/png")
    id=$(printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id",""))' 2>/dev/null || true)
    [[ -z "$id" ]] && { echo "Modrinth said: $out" >&2; exit 1; }
    gh variable set MODRINTH_PROJECT_ID -R "$REPO" --body "$id"
    echo "Created the private draft $id (https://modrinth.com/mod/kindred-spirit, visible only to you); MODRINTH_PROJECT_ID is set."
    ;;
  update-page)
    id=$(project_id); [[ -z "$id" ]] && { echo "Create it first."; exit 1; }
    body=$(python3 -c 'import json,sys; print(json.dumps({"body": open(sys.argv[1]).read().split("\n",2)[2].strip()}))' "$ROOT/docs/modrinth.md")
    curl -sS -f -X PATCH "$API/project/$id" -H "Authorization: $(token)" -H "User-Agent: $UA" \
      -H "Content-Type: application/json" -d "$body" && echo "Page updated."
    ;;
  show)
    id=$(project_id); [[ -z "$id" ]] && { echo "Not created yet."; exit 0; }
    out=$(curl -sS "$API/project/$id" -H "Authorization: $(token)" -H "User-Agent: $UA")  # (data, never run)
    python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get("title"), "|", d.get("status"), "| requested:", d.get("requested_status"), "| versions:", len(d.get("versions") or []))' "$out"
    ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
