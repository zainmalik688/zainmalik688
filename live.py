"""Draws live.svg from my real GitHub activity.

GitHub Actions runs this every 6 hours (see .github/workflows/snake.yml).
It only reads public data plus the contribution counts GitHub already
shows on my profile. Nothing is invented and nothing private is shown.
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape

USER = os.environ.get("GH_USER", "zainmalik688")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = sys.argv[1] if len(sys.argv) > 1 else "live.svg"
PKT = timezone(timedelta(hours=5))  # Pakistan time, no daylight saving

SANS = "'Segoe UI', Inter, Helvetica, Arial, sans-serif"
MONO = "Consolas, 'Cascadia Code', 'Courier New', monospace"
MAGMA = ["#51127c", "#7b2382", "#a3307e", "#cc4071", "#ec6a5c", "#fb9b67", "#fecf92", "#fcfdbf"]
UP, DOWN, SAME = "#5FD891", "#ec6a5c", "#8b98ad"


# ------------------------------------------------------------------ data
def api(url, body=None):
    headers = {"User-Agent": "profile-live-card", "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_days():
    """Daily contribution counts for the last year, oldest first."""
    query = ("query($u:String!){user(login:$u){contributionsCollection{contributionCalendar"
             "{weeks{contributionDays{date contributionCount}}}}}}")
    d = api("https://api.github.com/graphql", {"query": query, "variables": {"u": USER}})
    if d.get("errors") or not d.get("data", {}).get("user"):
        raise SystemExit(f"GitHub did not return the calendar: {d.get('errors')}")
    weeks = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [(day["date"], day["contributionCount"]) for w in weeks for day in w["contributionDays"]]
    return sorted(days)


def describe(e):
    """One short sentence for a public event, or None to skip it."""
    p, kind = e.get("payload", {}), e["type"]
    full = e["repo"]["name"]
    owner, _, name = full.partition("/")
    repo = "profile README" if full == f"{USER}/{USER}" else (name if owner == USER else full)
    repo = repo if len(repo) <= 24 else repo[:23] + "…"
    action = p.get("action")
    if kind == "PushEvent":
        return f"pushed code to {repo}"
    if kind == "CreateEvent" and p.get("ref_type") == "repository":
        return f"created {repo}"
    if kind == "PullRequestEvent" and action in ("opened", "merged"):
        return f"{action} a pull request in {repo}"
    if kind == "PullRequestEvent" and action == "closed" and p.get("pull_request", {}).get("merged"):
        return f"merged a pull request in {repo}"
    if kind == "IssuesEvent" and action in ("opened", "closed"):
        return f"{action} an issue in {repo}"
    if kind == "IssueCommentEvent":
        return f"commented in {repo}"
    if kind == "WatchEvent":
        return f"starred {repo}"
    if kind == "ForkEvent":
        return f"forked {repo}"
    if kind == "ReleaseEvent":
        return f"published a release of {repo}"
    if kind == "PublicEvent":
        return f"made {repo} public"
    return None


def get_activity(limit=4):
    items, seen = [], set()
    for e in api(f"https://api.github.com/users/{USER}/events/public?per_page=50"):
        text = describe(e)
        when = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")).astimezone(PKT)
        key = (text, when.date())
        if text and key not in seen:
            seen.add(key)
            items.append((text, when.strftime("%d %b").lstrip("0")))
        if len(items) == limit:
            break
    return items


# ------------------------------------------------------------------ maths
def stats(days):
    counts = [c for _, c in days]
    n = len(counts)
    s = {
        "week": sum(counts[-7:]), "prev_week": sum(counts[-14:-7]),
        "month": sum(counts[-30:]), "prev_month": sum(counts[-60:-30]),
        "active": sum(1 for c in counts[-30:] if c > 0),
    }
    best_i = max(range(n), key=lambda i: (counts[i], i))
    s["best"], s["best_date"] = counts[best_i], date.fromisoformat(days[best_i][0])
    s["quarter"], s["prev_quarter"] = sum(counts[-90:]), sum(counts[-180:-90])
    # the last 12 calendar months (the newest one is still in progress)
    months = {}
    for d, c in days:
        months[d[:7]] = months.get(d[:7], 0) + c
    s["bins"] = [(months[m], date.fromisoformat(m + "-01").strftime("%b")) for m in sorted(months)[-12:]]
    return s


def change(now, before, period, as_percent=True):
    """(text, colour) comparing two periods honestly."""
    if now == before:
        return f"same as {period}", SAME
    if before == 0:
        return f"▲ {period} had 0", UP
    diff = now - before
    if as_percent and now >= 2 * before:
        times = now / before
        return f"▲ {times:.0f}× the {period}" if times >= 10 else f"▲ {times:.1f}× the {period}", UP
    amount = f"{abs(diff) / before:.0%}" if as_percent else str(abs(diff))
    if diff > 0:
        return f"▲ {amount} more vs {period}", UP
    return f"▼ {amount} {'less' if as_percent else 'fewer'} vs {period}", DOWN


# ------------------------------------------------------------------ drawing
def tile(x, label, value, unit, note, note_color):
    return f"""<g transform="translate({x} 74)">
<rect width="222" height="96" rx="12" fill="#111723" stroke="#222a38"/>
<text x="16" y="25" font-family="{MONO}" font-size="12" fill="#8b98ad">{escape(label)}</text>
<text x="16" y="62" font-size="32" font-weight="700" fill="#e6edf3">{value}<tspan font-size="14" font-weight="400" fill="#8b98ad" dx="6">{escape(unit)}</tspan></text>
<text x="16" y="83" font-size="12" fill="{note_color}">{escape(note)}</text>
</g>"""


def render(days, activity, now):
    s = stats(days)
    wk_txt, wk_col = change(s["week"], s["prev_week"], "previous 7 days", as_percent=False)
    mo_txt, mo_col = change(s["month"], s["prev_month"], "previous 30 days")
    q_txt, q_col = change(s["quarter"], s["prev_quarter"], "previous 90 days")

    tiles = "\n".join([
        tile(30, "last 7 days", s["week"], "contributions", wk_txt, wk_col),
        tile(266, "last 30 days", s["month"], "contributions", mo_txt, mo_col),
        tile(502, "active days", s["active"], "of the last 30", "days with 1+ contribution", SAME),
        tile(738, "busiest day", s["best"], "contributions",
             f"on {s['best_date'].strftime('%d %b %Y').lstrip('0')}", SAME),
    ])

    # 12-month bars
    top = max(v for v, _ in s["bins"]) or 1
    bx, base, bh, step = 46, 352, 112, 46
    bars = []
    for i, (v, month) in enumerate(s["bins"]):
        h = max(3, round(bh * v / top))
        col = MAGMA[min(len(MAGMA) - 1, round((len(MAGMA) - 1) * v / top))] if v else "#1b2230"
        x = bx + i * step
        delay = f"{0.15 + i * 0.06:.2f}s"
        bars.append(
            f'<rect x="{x}" y="{base - h}" width="30" height="{h}" rx="4" fill="{col}">'
            f'<animate attributeName="height" from="0" to="{h}" dur="0.7s" begin="{delay}" fill="freeze"/>'
            f'<animate attributeName="y" from="{base}" to="{base - h}" dur="0.7s" begin="{delay}" fill="freeze"/></rect>'
            f'<text x="{x + 15}" y="{base - h - 7}" text-anchor="middle" font-family="{MONO}" font-size="11" fill="#8b98ad">{v}</text>'
            f'<text x="{x + 15}" y="{base + 18}" text-anchor="middle" font-family="{MONO}" font-size="11" fill="#5a6270">{month}</text>')

    # latest public activity
    rows = []
    for i, (text, when) in enumerate(activity):
        y = 252 + i * 32
        rows.append(f'<circle cx="652" cy="{y - 4}" r="4" fill="#fb9b67"/>'
                    f'<text x="666" y="{y}" font-size="13" fill="#e6edf3">{escape(text)}</text>'
                    f'<text x="970" y="{y}" text-anchor="end" font-family="{MONO}" font-size="12" fill="#5a6270">{escape(when)}</text>')
    if not rows:
        rows.append('<text x="644" y="252" font-size="14" fill="#8b98ad">No public activity in the last 90 days.</text>')

    synced = now.astimezone(PKT).strftime("%d %b %Y, %H:%M PKT").lstrip("0")
    W, H = 1000, 400
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{SANS}">
<title>Live GitHub activity for {USER}</title>
<defs><clipPath id="frame"><rect width="{W}" height="{H}" rx="22"/></clipPath></defs>
<g clip-path="url(#frame)">
<rect width="{W}" height="{H}" fill="#0a0e15"/>
<text x="30" y="44" font-family="{MONO}" font-size="16" fill="#5FD891">$ git log --author=zain --since="1 year"</text>
<circle cx="716" cy="39" r="5" fill="#5FD891"><animate attributeName="opacity" values="1;0.25;1" dur="1.6s" repeatCount="indefinite"/></circle>
<text x="970" y="44" text-anchor="end" font-family="{MONO}" font-size="12" fill="#8b98ad">live · synced {escape(synced)}</text>
{tiles}
<text x="30" y="214" font-size="15" font-weight="600" fill="#e6edf3">Contributions per month</text>
<text x="590" y="214" text-anchor="end" font-size="13" fill="{q_col}">last 90 days: {escape(q_txt)}</text>
<path d="M30 {base + 0.5}H600" stroke="#222a38"/>
{''.join(bars)}
<path d="M622 196V374" stroke="#222a38"/>
<text x="644" y="214" font-size="15" font-weight="600" fill="#e6edf3">Latest public activity</text>
{''.join(rows)}
</g>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="21" fill="none" stroke="#30363d" stroke-width="2"/>
</svg>
"""


def main():
    svg = render(get_days(), get_activity(), datetime.now(timezone.utc))
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
