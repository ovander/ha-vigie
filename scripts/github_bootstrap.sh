#!/usr/bin/env bash
# One-shot GitHub setup for ha-vigie. Run once from the repository root.
# Requires: git, gh (authenticated: `gh auth login`), perl.
set -euo pipefail

REPO="ha-vigie"
DESCRIPTION="Home Assistant integration for boats: reads an AIS receiver over NMEA 0183 (serial), exposes own position and AIS traffic, and raises CPA/TCPA collision-risk alerts. Local, no cloud."
TOPICS="home-assistant,hacs,hacs-integration,ais,nmea0183,aivdm,sailing,boat,marine,collision-avoidance"

OWNER="$(gh api user --jq .login)"
echo "==> GitHub account: $OWNER"

# 1. Replace OWNER placeholders (manifest, README, CODEOWNERS)
for f in $(grep -rl --exclude-dir=.git --exclude-dir=scripts 'OWNER' . || true); do
  perl -pi -e "s{\@OWNER}{\@$OWNER}g; s{github\.com/OWNER/}{github.com/$OWNER/}g" "$f"
done

# 2. Initial commit
if [ ! -d .git ]; then git init -b main; fi
git add -A
git commit -m "chore: bootstrap Vigie (P0 AIS decoder, skeleton, CI, docs)"

# 3. Create the repository (public: required for HACS and free branch protection)
gh repo create "$REPO" --public --description "$DESCRIPTION" --source . --remote origin
gh repo edit "$OWNER/$REPO" \
  --add-topic "$TOPICS" \
  --enable-issues --enable-wiki=false --enable-projects=false \
  --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false \
  --delete-branch-on-merge

# 4. Push
git push -u origin main

# 5. Labels (aligned with SPEC phases, layers and open decisions)
lbl() { gh label create "$1" --color "$2" --description "$3" --force -R "$OWNER/$REPO"; }
lbl "phase:P1"        "0e8a16" "SPEC P1 — base: transport, GPS, own boat, AIS table"
lbl "phase:P2"        "1d76db" "SPEC P2 — traffic: CPA/TCPA, alerts, watch list"
lbl "phase:P3"        "5319e7" "SPEC P3 — AIS static data"
lbl "phase:P4"        "c5def5" "SPEC P4 — instruments and performance"
lbl "layer:transport" "fbca04" "hub.py — serial I/O"
lbl "layer:protocol"  "fef2c0" "nmea/ — pure Python parsers"
lbl "layer:traffic"   "d93f0b" "traffic.py — CPA/TCPA"
lbl "layer:entities"  "bfd4f2" "sensor / binary_sensor / device_tracker"
lbl "open-decision"   "b60205" "Tracks an OD-xx or TP-xx item from the docs"
lbl "test"            "0052cc" "Test protocol work (TEST-001)"
lbl "capture"         "006b75" "Raw NMEA capture contributed as fixture"
lbl "safety"          "e11d21" "Could affect collision-risk behaviour"

# 6. Milestones = SPEC roadmap phases
ms() { gh api "repos/$OWNER/$REPO/milestones" -f title="$1" -f description="$2" >/dev/null; }
ms "P1 Base"        "Transport, GPS parsers, coordinator, own-boat entities, AIS target table, diagnostics"
ms "P2 Traffic"     "CPA/TCPA, closest threat, collision_risk, watch-list trackers"
ms "P3 Static data" "AIS types 5/24: names, ship type, dimensions"
ms "P4 Instruments" "Wind/depth sources and sailing performance (needs hardware)"

# 7. Branch protection on main: PR + green CI, linear history (owner can bypass)
gh api -X PUT "repos/$OWNER/$REPO/branches/main/protection" --input - <<JSON
{
  "required_status_checks": { "strict": true, "contexts": ["lint", "unit", "hassfest", "hacs"] },
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

# 8. Private vulnerability reporting (SECURITY.md)
gh api -X PUT "repos/$OWNER/$REPO/private-vulnerability-reporting" >/dev/null || \
  echo "   (enable it manually: Settings → Code security → Private vulnerability reporting)"

echo "==> Done: https://github.com/$OWNER/$REPO"
echo "    Check the Actions tab: lint, unit, hassfest and hacs should all be green."
