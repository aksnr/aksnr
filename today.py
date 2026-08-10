#!/usr/bin/env python3
"""
today.py
Neofetch-style SVG card generator for aksnr/aksnr.
Generates dark_mode.svg and light_mode.svg with live GitHub stats.

Usage:
    GH_TOKEN=<token> python today.py
"""

import os
import sys
import json
import datetime
import urllib.request

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION  (edit these)
# ─────────────────────────────────────────────────────────────────────────────
GITHUB_USERNAME = "aksnr"
DOB             = datetime.date(2002, 6, 26)
FULL_NAME       = "Akash S Nair"
EMAIL           = "aksnr@protonmail.com"
LINKEDIN_URL    = "https://www.linkedin.com/in/aksnr"

# SVG geometry
SVG_WIDTH   = 820
PADDING_X   = 38
PADDING_Y   = 46
LINE_HEIGHT = 23

# Dot-leader key column width (characters in monospace)
KEY_COL = 24

# ─────────────────────────────────────────────────────────────────────────────
#  THEMES
# ─────────────────────────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg"      : "#0d1117",
        "border"  : "#30363d",
        "accent"  : "#f78166",   # username colour
        "at"      : "#ffa657",   # @dev colour
        "sep"     : "#21262d",   # ── separator lines
        "section" : "#3fb950",   # ── Section Header ──
        "key"     : "#79c0ff",   # key name
        "dot"     : "#3d444d",   # ............
        "val"     : "#e6edf3",   # value text
        "dim"     : "#6e7681",   # · · · dividers / dim text
    },
    "light": {
        "bg"      : "#ffffff",
        "border"  : "#d0d7de",
        "accent"  : "#cf222e",
        "at"      : "#953800",
        "sep"     : "#d0d7de",
        "section" : "#116329",
        "key"     : "#0550ae",
        "dot"     : "#c9d1d9",
        "val"     : "#24292f",
        "dim"     : "#6e7781",
    },
}

SWATCHES = {
    "dark" : ["#ff7b72","#ffa657","#e3b341","#3fb950",
               "#58a6ff","#bc8cff","#f778ba","#8b949e"],
    "light": ["#cf222e","#953800","#9a6700","#116329",
               "#0550ae","#8250df","#bf3989","#57606a"],
}

# ─────────────────────────────────────────────────────────────────────────────
#  UPTIME CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────
def uptime_from_dob(dob: datetime.date) -> str:
    today  = datetime.date.today()
    years  = today.year  - dob.year
    months = today.month - dob.month
    days   = today.day   - dob.day

    if days < 0:
        months -= 1
        # how many days in the previous month?
        pm  = today.month - 1 or 12
        py  = today.year if today.month > 1 else today.year - 1
        nm  = pm % 12 + 1
        ny  = py if pm < 12 else py + 1
        days += (datetime.date(ny, nm, 1) - datetime.date(py, pm, 1)).days

    if months < 0:
        years  -= 1
        months += 12

    return f"{years} years, {months} months, {days} days"

# ─────────────────────────────────────────────────────────────────────────────
#  GITHUB GRAPHQL + REST HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _gh_request(token: str, url: str, payload: bytes | None = None) -> dict | list:
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type" : "application/json",
            "User-Agent"   : "aksnr-readme-bot/2.0",
            "Accept"       : "application/vnd.github+json",
        },
        method="POST" if payload else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_github_stats(token: str) -> dict:
    # ── GraphQL: basic profile data ───────────────────────────────────────
    gql_body = json.dumps({
        "query": """
        query($login: String!) {
          user(login: $login) {
            repositories(
              ownerAffiliations: OWNER
              isFork: false
              first: 100
              orderBy: {field: PUSHED_AT, direction: DESC}
            ) {
              totalCount
              nodes { stargazerCount nameWithOwner }
            }
            contributionsCollection {
              totalCommitContributions
              totalPullRequestContributions
            }
            followers { totalCount }
          }
        }
        """,
        "variables": {"login": GITHUB_USERNAME},
    }).encode()

    gql_data = _gh_request(token, "https://api.github.com/graphql", gql_body)
    user     = gql_data["data"]["user"]

    repos     = user["repositories"]["totalCount"]
    stars     = sum(n["stargazerCount"] for n in user["repositories"]["nodes"])
    commits   = user["contributionsCollection"]["totalCommitContributions"]
    followers = user["followers"]["totalCount"]

    # ── REST: contributor stats (additions / deletions) ───────────────────
    repo_names = [n["nameWithOwner"] for n in user["repositories"]["nodes"]]
    additions = deletions = 0

    for repo in repo_names[:25]:          # cap to avoid rate-limit burn
        owner, name = repo.split("/", 1)
        try:
            contribs = _gh_request(
                token,
                f"https://api.github.com/repos/{owner}/{name}/stats/contributors",
            )
            if not isinstance(contribs, list):
                continue
            for c in contribs:
                if c.get("author", {}).get("login", "").lower() == GITHUB_USERNAME.lower():
                    for w in c.get("weeks", []):
                        additions += w.get("a", 0)
                        deletions += w.get("d", 0)
        except Exception:
            pass  # skip repos with no stats yet

    return {
        "repos"    : repos,
        "stars"    : stars,
        "commits"  : commits,
        "followers": followers,
        "additions": additions,
        "deletions": deletions,
        "loc"      : additions + deletions,
    }

# ─────────────────────────────────────────────────────────────────────────────
#  LAYOUT BUILDER  →  list of (text, style, url|None) tuples
# ─────────────────────────────────────────────────────────────────────────────
def _kv(key: str, val: str, url: str | None = None) -> tuple:
    """Build a dot-leader row.  KEY........... VALUE  (url makes value a link)"""
    dots = max(2, KEY_COL - len(key))
    return (f"{key}{'.' * dots} {val}", "kv", url)


def build_lines(stats: dict, uptime: str) -> list[tuple]:
    L = []

    def add(text, style="val"):
        L.append((text, style, None))

    # ── Header ────────────────────────────────────────────────────────────
    add(f"akash@dev", "header")
    add("─" * 62, "sep")

    # ── System ────────────────────────────────────────────────────────────
    L.append(_kv("OS",     "Linux  /  Windows 11"))
    L.append(_kv("Uptime", uptime))
    L.append(_kv("Host",   FULL_NAME))
    add("", "blank")

    # ── Stack & Languages ─────────────────────────────────────────────────
    add("── Stack & Languages ─────────────────────────────", "section")
    add("·" * 62, "dim")
    L.append(_kv("Languages.Programming",  "JavaScript, Python, Bash"))
    L.append(_kv("Stack.Web & Frameworks", "React.js, Express.js, Node.js, HTML5, CSS3"))
    L.append(_kv("Databases",             "MongoDB, PostgreSQL, SQL, Git"))
    L.append(_kv("Focus.Areas",           "MERN Stack, Systems & Linux, Cybersecurity"))
    add("", "blank")

    # ── Contact ──────────────────────────────────────────────────────────
    add("── Contact ────────────────────────────────────", "section")
    add("·" * 62, "dim")
    L.append(_kv("Email",    EMAIL,    f"mailto:{EMAIL}"))
    L.append(_kv("LinkedIn", "aksnr",  LINKEDIN_URL))
    add("", "blank")

    # ── GitHub Stats ──────────────────────────────────────────────────────
    add("── GitHub Stats ──────────────────────────────────", "section")
    add("·" * 62, "dim")
    L.append(_kv("Repos",         str(stats["repos"])))
    L.append(_kv("Stars",         str(stats["stars"])))
    L.append(_kv("Commits",       str(stats["commits"])))
    L.append(_kv("Followers",     str(stats["followers"])))
    L.append(_kv("Lines of Code",
                 f"{stats['loc']:,}  "
                 f"(+{stats['additions']:,} / -{stats['deletions']:,})"))
    add("", "blank")

    # ── Colour swatch ─────────────────────────────────────────────────────
    add("  ● ● ● ● ● ● ● ●", "swatch")

    return L

# ─────────────────────────────────────────────────────────────────────────────
#  SVG RENDERER
# ─────────────────────────────────────────────────────────────────────────────
def _esc(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def render_svg(lines: list[tuple], theme_name: str, out_path: str) -> None:
    t  = THEMES[theme_name]
    sw = SWATCHES[theme_name]
    h  = PADDING_Y * 2 + len(lines) * LINE_HEIGHT + 20

    parts: list[str] = []

    # ── Outer shell ───────────────────────────────────────────────────────
    parts.append(f"""\
<svg xmlns="http://www.w3.org/2000/svg"
     width="{SVG_WIDTH}" height="{h}"
     viewBox="0 0 {SVG_WIDTH} {h}"
     role="img" aria-label="{GITHUB_USERNAME}@dev — GitHub card">
  <title>{GITHUB_USERNAME}@dev — GitHub Stats Card</title>
  <defs>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&amp;display=swap');
      text {{
        font-family: "JetBrains Mono","Cascadia Code","Fira Code",Consolas,monospace;
        font-size: 13px;
      }}
    </style>
  </defs>

  <!-- Card background -->
  <rect width="{SVG_WIDTH}" height="{h}" rx="12" ry="12"
        fill="{t['bg']}" stroke="{t['border']}" stroke-width="1.5"/>

""")

    y = PADDING_Y

    for item in lines:
        text, style, url = item[0], item[1], item[2] if len(item) > 2 else None
        x = PADDING_X

        # ── blank spacer ──────────────────────────────────────────────────
        if style == "blank":
            y += LINE_HEIGHT
            continue

        # ── colour swatch circles ─────────────────────────────────────────
        if style == "swatch":
            cx = x + 8
            for colour in sw:
                parts.append(
                    f'  <circle cx="{cx}" cy="{y - 5}" r="7" fill="{colour}"/>\n'
                )
                cx += 26
            y += LINE_HEIGHT
            continue

        # ── header  "akash@dev" ───────────────────────────────────────────
        if style == "header":
            at_pos  = text.index("@")
            u_part  = _esc(text[:at_pos])
            at_part = _esc(text[at_pos:])
            parts.append(
                f'  <text x="{x}" y="{y}" font-weight="700" font-size="15px">'
                f'<tspan fill="{t["accent"]}">{u_part}</tspan>'
                f'<tspan fill="{t["at"]}">{at_part}</tspan>'
                f'</text>\n'
            )

        # ── ─── separator ─────────────────────────────────────────────────
        elif style == "sep":
            parts.append(
                f'  <text x="{x}" y="{y}" fill="{t["sep"]}">'
                f'{_esc(text)}</text>\n'
            )

        # ── ── Section Header ────────────────────────────────────────────
        elif style == "section":
            parts.append(
                f'  <text x="{x}" y="{y}" fill="{t["section"]}"'
                f' font-weight="700">{_esc(text)}</text>\n'
            )

        # ── · · · dim divider ────────────────────────────────────────────
        elif style == "dim":
            parts.append(
                f'  <text x="{x}" y="{y}" fill="{t["dim"]}">'
                f'{_esc(text)}</text>\n'
            )

        # ── KEY........... value ──────────────────────────────────────────
        elif style == "kv":
            # Locate the dot run
            dot_start = 0
            while dot_start < len(text) and text[dot_start] != ".":
                dot_start += 1
            dot_end = dot_start
            while dot_end < len(text) and text[dot_end] == ".":
                dot_end += 1

            k_part = _esc(text[:dot_start])
            d_part = _esc(text[dot_start:dot_end])
            v_part = _esc(text[dot_end:])

            if url:
                # Value becomes a clickable hyperlink
                v_node = (
                    f'<a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">'
                    f'<tspan fill="{t["key"]}" text-decoration="underline">{v_part}</tspan>'
                    f'</a>'
                )
            else:
                v_node = f'<tspan fill="{t["val"]}">{v_part}</tspan>'

            parts.append(
                f'  <text x="{x}" y="{y}">'
                f'<tspan fill="{t["key"]}" font-weight="600">{k_part}</tspan>'
                f'<tspan fill="{t["dot"]}">{d_part}</tspan>'
                f'{v_node}'
                f'</text>\n'
            )

        # ── generic value ─────────────────────────────────────────────────
        else:
            if text.strip():
                parts.append(
                    f'  <text x="{x}" y="{y}" fill="{t["val"]}">'
                    f'{_esc(text)}</text>\n'
                )

        y += LINE_HEIGHT

    parts.append("</svg>\n")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.writelines(parts)

    print(f"  ✔  {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GH_TOKEN or GITHUB_TOKEN environment variable is required.",
              file=sys.stderr)
        sys.exit(1)

    # 1. Uptime
    print("→  Calculating uptime …")
    uptime = uptime_from_dob(DOB)
    print(f"   {uptime}")

    # 2. GitHub stats
    print("→  Fetching GitHub stats …")
    try:
        stats = fetch_github_stats(token)
    except Exception as exc:
        print(f"ERROR fetching stats: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"   repos={stats['repos']}  stars={stats['stars']}  "
          f"commits={stats['commits']}  followers={stats['followers']}")
    print(f"   loc={stats['loc']:,}  "
          f"(+{stats['additions']:,} / -{stats['deletions']:,})")

    # 3. Build layout
    print("→  Building SVG lines …")
    lines = build_lines(stats, uptime)

    # 4. Render
    print("→  Rendering SVGs …")
    render_svg(lines, "dark",  "dark_mode.svg")
    render_svg(lines, "light", "light_mode.svg")

    print("\n✅  Done!  dark_mode.svg & light_mode.svg are ready.")


if __name__ == "__main__":
    main()
