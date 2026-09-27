import html
import os
import re

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SVYB Dribble 10", page_icon="🏀", layout="wide")

GRADE_ORDER = ["1st Grade", "2nd Grade", "3rd Grade", "4th Grade", "5th Grade", "6th Grade"]
COLUMN_ALIASES = {
    "display_name": ["display name", "player display name", "player"],
    "grade": ["grade", "player grade"],
    "session_date": ["session date", "date completed", "workout date"],
    "week": ["week", "challenge week"],
    "minutes": ["minutes", "workout minutes"],
    "parent_confirmed": ["parent confirmed", "parent/guardian confirmed", "confirmed"],
    "show_public": ["show on public leaderboard", "public consent", "show publicly"],
}
COMMUNITY_GOAL = 1000


def _yes(value) -> bool:
    return str(value).strip().lower() in {"yes", "y", "true", "1", "approved", "checked"}


def _grade(value) -> str:
    raw = str(value).strip().lower()
    match = re.search(r"([1-6])", raw)
    if match:
        n = int(match.group(1))
        suffix = "th" if n == 6 else ["", "st", "nd", "rd", "th", "th"][n]
        return f"{n}{suffix} Grade"
    words = {"first": "1st Grade", "second": "2nd Grade", "third": "3rd Grade", "fourth": "4th Grade", "fifth": "5th Grade", "sixth": "6th Grade"}
    for word, label in words.items():
        if word in raw:
            return label
    return "Other"


def _week(value) -> str:
    raw = str(value).strip().lower()
    match = re.search(r"(?:week\s*)?([1-3])", raw)
    return f"Week {match.group(1)}" if match else str(value).strip()


def _find_column(columns, key):
    normalized = {str(column).strip().lower(): column for column in columns}
    for alias in COLUMN_ALIASES[key]:
        if alias in normalized:
            return normalized[alias]
    return None


def prepare_data(raw: pd.DataFrame) -> pd.DataFrame:
    selected = {key: _find_column(raw.columns, key) for key in COLUMN_ALIASES}
    required = ["grade", "session_date", "minutes", "parent_confirmed", "show_public"]
    missing = [key for key in required if selected[key] is None]
    if missing:
        raise ValueError(f"The Dashboard Feed is missing required column(s): {', '.join(missing)}.")

    data = pd.DataFrame()
    for key, column in selected.items():
        data[key] = raw[column] if column is not None else ""

    data["grade"] = data["grade"].map(_grade)
    data["session_date"] = pd.to_datetime(data["session_date"], errors="coerce").dt.date
    data["minutes"] = pd.to_numeric(data["minutes"], errors="coerce").fillna(0)
    data["parent_confirmed"] = data["parent_confirmed"].map(_yes)
    data["show_public"] = data["show_public"].map(_yes)
    data["display_name"] = data["display_name"].fillna("").astype(str).str.strip()
    data["week"] = data["week"].fillna("").map(_week)
    data = data[
        data["parent_confirmed"] & (data["minutes"] >= 10)
        & data["session_date"].notna() & data["grade"].isin(GRADE_ORDER)
    ].copy()
    data["sessions"] = 1
    return data


@st.cache_data(ttl=30, show_spinner=False)
def load_csv(url: str) -> pd.DataFrame:
    return pd.read_csv(url)


def _milestone_badges(total: int) -> str:
    badges = []
    if total >= 5:
        badges.append('<span class="badge badge-fire" title="5 workouts">🔥 5</span>')
    if total >= 10:
        badges.append('<span class="badge badge-star" title="10 workouts">⭐ 10</span>')
    if total >= 15:
        badges.append('<span class="badge badge-trophy" title="15 workouts">🏆 15</span>')
    return "".join(badges)


def _rank_icon(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, str(rank))


def render_grade_board(grade: str, public_data: pd.DataFrame):
    grade_data = public_data[public_data["grade"] == grade]
    total_grade_sessions = int(grade_totals.get(grade, 0))
    st.markdown(f'<div class="grade-title">{html.escape(grade)} <span>{total_grade_sessions} TOTAL</span></div>', unsafe_allow_html=True)
    if grade_data.empty:
        st.markdown('<div class="empty-board">No players have opted into name display yet. Their sessions still count toward the grade total. 🏀</div>', unsafe_allow_html=True)
        return

    players = (grade_data.groupby("display_name", as_index=False)
               .agg(Total=("sessions", "sum"), Latest=("session_date", "max"))
               .sort_values(["Total", "Latest", "display_name"], ascending=[False, False, True]))
    players["Rank"] = players["Total"].rank(method="min", ascending=False).astype(int)
    rows = []
    for player in players.itertuples(index=False):
        rank = int(player.Rank)
        total = int(player.Total)
        tickets = total // 3
        name = html.escape(str(player.display_name))
        # One basketball for every completed session. Keep the count alongside the icons for clarity.
        ball_count = min(total, 15)
        balls = "🏀" * ball_count
        overflow = f"<span class='more-balls'>+{total - 15}</span>" if total > 15 else ""
        rows.append(
            f'<div class="player-row rank-{rank if rank <= 3 else "other"}">'
            f'<div class="player-top"><span class="rank">{_rank_icon(rank)}</span>'
            f'<span class="player-name">{name}</span><span class="session-count">{total} session{"s" if total != 1 else ""}</span></div>'
            f'<div class="player-bottom"><span class="balls" aria-label="{total} completed sessions">{balls}{overflow}</span>'
            f'<span class="player-rewards"><span class="ticket" title="One raffle ticket for every three workouts">🎟️ {tickets}</span>'
            f'<span class="badges">{_milestone_badges(total)}</span></span></div></div>'
        )
    st.markdown('<div class="leaderboard">' + "".join(rows) + "</div>", unsafe_allow_html=True)


st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@500;700;800;900&display=swap');
.stApp { background: #f3f5f8; color-scheme:light; }
html, body, [class*="css"] { font-family: 'Nunito', sans-serif; }
.stApp, .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stMetricLabel"], .stApp [data-testid="stMetricValue"], .stApp [data-testid="stMetricDelta"] { color:#17191f !important; }
.stApp [data-testid="stCaptionContainer"] p { color:#383c45 !important; }
.stApp [data-testid="stMetricLabel"] *, .stApp [data-testid="stMetricValue"] * { color:#17191f !important; }
.stApp h1, .stApp h2, .stApp h3 { color:#17191f !important; }
.hero { background: linear-gradient(115deg,#17191f 0%,#292d35 65%,#c8202f 100%); color:white; padding:24px 30px; border-radius:18px; margin:0 0 16px; box-shadow:0 8px 24px #13172122; }
.hero h1 { font-size:2.35rem; margin:0; color:white !important; font-weight:900; }
.hero p { margin:5px 0 0; color:#fff !important; font-size:1rem; }
.section-heading { font-size:1.45rem; font-weight:900; color:#20232b; margin:20px 0 4px; }
.grade-title { font-weight:900; font-size:1.15rem; color:#fff; background:#22252d; border-radius:12px 12px 0 0; padding:12px 14px; margin-top:10px; }
.grade-title span { float:right; color:#ffc928; font-size:.7rem; letter-spacing:.1em; padding-top:5px; }
.grade-race-card { background:white; border:1px solid #e2e5ea; border-radius:14px; padding:12px 14px; margin:4px 0 8px; box-shadow:0 3px 10px #1c253008; }
.grade-race-top { display:flex; justify-content:space-between; align-items:center; color:#292d35; font-weight:900; }
.grade-race-score { color:#c8202f; font-size:1.35rem; font-weight:900; }
.grade-race-bar { height:7px; background:#edf0f4; border-radius:6px; margin-top:8px; overflow:hidden; }
.grade-race-fill { height:100%; background:linear-gradient(90deg,#c8202f,#f05a36); border-radius:6px; }
.grade-leader { color:#926600; background:#fff2c2; border-radius:8px; padding:2px 6px; font-size:.62rem; letter-spacing:.05em; }
.leaderboard, .empty-board { background:white; border:1px solid #e2e5ea; border-top:0; border-radius:0 0 12px 12px; padding:6px 10px; min-height:60px; box-shadow:0 3px 10px #1c253008; }
.empty-board { color:#7b808a; padding:18px 14px; }
.player-row { border-bottom:1px solid #eef0f3; padding:8px 2px; }
.player-row:last-child { border-bottom:0; }
.player-top { display:flex; align-items:center; gap:7px; min-width:0; }
.rank { min-width:25px; font-weight:900; color:#30343d; font-size:.95rem; }
.player-name { font-weight:800; color:#20232b; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.session-count { color:#727781; font-size:.73rem; font-weight:700; white-space:nowrap; }
.player-bottom { padding-left:32px; display:flex; justify-content:space-between; align-items:center; gap:4px; min-height:20px; }
.player-rewards { display:flex; flex-wrap:wrap; gap:3px; justify-content:flex-end; align-items:center; }
.ticket { color:#642600; background:#ffe9d8; font-size:.64rem; padding:2px 5px; border-radius:9px; font-weight:900; white-space:nowrap; }
.balls { font-size:.73rem; letter-spacing:-2px; white-space:nowrap; }
.more-balls { font-size:.72rem; letter-spacing:0; color:#6d727c; font-weight:800; margin-left:4px; }
.badges { display:flex; gap:3px; justify-content:flex-end; }
.badge { font-size:.64rem; padding:2px 5px; border-radius:9px; font-weight:900; white-space:nowrap; }
.badge-fire { background:#fff0df; color:#a94300; }
.badge-star { background:#fff7cc; color:#725400; }
.badge-trophy { background:#e9f0ff; color:#244a9a; }
.stMetric { background:white; border:1px solid #e4e6eb; border-radius:14px; padding:12px; }
.community-ladder { display:flex; flex-wrap:wrap; gap:6px; margin:5px 0 10px; }
.mile { border-radius:14px; padding:5px 9px; font-size:.77rem; font-weight:900; color:#545b66; background:#e3e6ec; }
.mile.hit { color:#fff; background:#187143; }
.mile.next { color:#fff; background:#c8202f; box-shadow:0 0 0 2px #ffc928; }
@media(max-width:760px) { .hero h1 {font-size:1.8rem;} .player-name {font-size:.86rem;} .session-count {font-size:.65rem;} }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>🏀 SVYB DRIBBLE 10</h1><p>Every session counts. Keep the ball moving and climb your grade leaderboard!</p></div>', unsafe_allow_html=True)

csv_url = st.secrets.get("dashboard_csv_url", os.getenv("DASHBOARD_CSV_URL", "")).strip()
if not csv_url:
    st.info("The dashboard is ready for its Google Sheets feed. Add `dashboard_csv_url` to Streamlit secrets using the published CSV URL for the sanitized Dashboard Feed tab.")
    st.markdown("**Privacy setup:** publish only the separate `Dashboard Feed` tab. Never publish the Google Form response tab, parent emails, or players’ full names.")
    st.stop()

try:
    raw = load_csv(csv_url)
    data = prepare_data(raw)
except Exception as exc:
    st.error(f"Could not load the Dashboard Feed: {exc}")
    st.caption("Check that the URL is the published CSV for the sanitized Dashboard Feed tab and that its headers match the setup guide.")
    st.stop()

challenge_start = st.secrets.get("challenge_start", os.getenv("CHALLENGE_START", "")).strip()
challenge_end = st.secrets.get("challenge_end", os.getenv("CHALLENGE_END", "")).strip()
if challenge_start:
    start = pd.to_datetime(challenge_start, errors="coerce")
    if not pd.isna(start):
        data = data[data["session_date"] >= start.date()]
if challenge_end:
    end = pd.to_datetime(challenge_end, errors="coerce")
    if not pd.isna(end):
        data = data[data["session_date"] <= end.date()]

public_data = data[data["show_public"] & data["display_name"].ne("")].copy()
sessions = len(data)
minutes = int(data["minutes"].sum())
public_players = public_data[["grade", "display_name"]].drop_duplicates().shape[0]
grade_totals = data.groupby("grade").size().reindex(GRADE_ORDER, fill_value=0)

m1, m2, m3 = st.columns(3)
m1.metric("🏀 Total SVYB Workouts", f"{sessions:,}")
m2.metric("⏱️ Total SVYB Dribbling Minutes", f"{minutes:,}")
m3.metric("⭐ Players on leaderboard", f"{public_players:,}")
progress = min(sessions / COMMUNITY_GOAL, 1.0)
st.markdown(f'<div class="section-heading">SVYB community goal <span style="color:#c8202f">{sessions:,} / {COMMUNITY_GOAL:,} workouts</span></div>', unsafe_allow_html=True)
st.progress(progress, text=f"{progress:.0%} of the way to {COMMUNITY_GOAL:,} workouts")
next_milestone = min(((sessions // 100) + 1) * 100, COMMUNITY_GOAL)
milestone_note = "🎉 1,000-workout goal reached!" if sessions >= COMMUNITY_GOAL else f"Next team milestone: {next_milestone:,} workouts"
st.markdown(f"**{milestone_note}**", unsafe_allow_html=False)
milestone_html = []
for milestone in range(100, COMMUNITY_GOAL + 1, 100):
    css_class = "mile hit" if sessions >= milestone else ("mile next" if milestone == next_milestone else "mile")
    marker = "✓ " if sessions >= milestone else ""
    milestone_html.append(f'<span class="{css_class}">{marker}{milestone:,}</span>')
st.markdown('<div class="community-ladder">' + "".join(milestone_html) + "</div>", unsafe_allow_html=True)
st.caption("Players appear by display name only when their family has opted in. Every parent-confirmed 10-minute session counts toward the team goal.")

st.markdown('<div class="section-heading">Grade leaderboards</div>', unsafe_allow_html=True)
st.caption("Every opted-in player is listed, ranked by completed workouts. Each 🏀 represents one session. Players earn one raffle ticket for every three workouts, shown beside their name.")
st.caption("Milestone badges unlock at 5, 10, and 15 sessions. Players whose families did not opt in to public display still count toward grade and community totals and remain eligible for the drawing.")
for row_start in (0, 3):
    cols = st.columns(3, gap="medium")
    for col, grade in zip(cols, GRADE_ORDER[row_start:row_start + 3]):
        with col:
            render_grade_board(grade, public_data)

st.markdown('<div class="section-heading">Grade-vs-grade race</div>', unsafe_allow_html=True)
st.caption("Cumulative parent-confirmed workouts by grade. These totals include sessions from families who chose not to show a player name.")
max_grade_total = int(grade_totals.max()) if len(grade_totals) else 0
ranked_grades = sorted(GRADE_ORDER, key=lambda grade: (-int(grade_totals[grade]), GRADE_ORDER.index(grade)))
for row_start in (0, 3):
    cols = st.columns(3, gap="medium")
    for position, (col, grade) in enumerate(zip(cols, ranked_grades[row_start:row_start + 3]), start=row_start + 1):
        total = int(grade_totals[grade])
        width = int(total / max_grade_total * 100) if max_grade_total else 0
        leading = max_grade_total > 0 and total == max_grade_total
        leader_badge = '<span class="grade-leader">🏆 GRADE LEADER</span>' if leading else f'<span class="grade-leader">#{position}</span>'
        with col:
            st.markdown(
                f'<div class="grade-race-card"><div class="grade-race-top"><span>{html.escape(grade)}</span>{leader_badge}</div>'
                f'<div class="grade-race-score">{total:,} workouts</div>'
                f'<div class="grade-race-bar"><div class="grade-race-fill" style="width:{width}%"></div></div></div>',
                unsafe_allow_html=True,
            )

st.markdown('<div class="section-heading">Community activity by day</div>', unsafe_allow_html=True)
if not data.empty:
    daily_counts = data.groupby("session_date").size().sort_index()
    values = daily_counts.astype(int).tolist()
    dates = [day.strftime("%b %d").replace(" 0", " ") for day in daily_counts.index]
    chart_width, chart_height = 800, 300
    left, right, top, bottom = 48, 18, 22, 42
    plot_width = chart_width - left - right
    plot_height = chart_height - top - bottom
    max_value = max(values) if values else 1
    points = [
        (left + (plot_width * i / max(len(values) - 1, 1)), top + plot_height * (1 - value / max_value))
        for i, value in enumerate(values)
    ]
    path = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points))
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#c8202f" />' for x, y in points)
    labels = "".join(
        f'<text x="{x:.1f}" y="{chart_height - 12}" text-anchor="middle" font-size="13" fill="#252831">{dates[i]}</text>'
        for i, (x, _) in enumerate(points)
    )
    chart = (
        f'<div style="background:#fff;border:1px solid #e2e5ea;border-radius:12px;padding:10px">'
        f'<svg viewBox="0 0 {chart_width} {chart_height}" role="img" aria-label="Daily completed workouts line graph" style="width:100%;height:auto">'
        f'<text x="8" y="18" font-size="12" fill="#252831">{max_value}</text>'
        f'<text x="8" y="{top + plot_height}" font-size="12" fill="#252831">0</text>'
        f'<line x1="{left}" y1="{top + plot_height}" x2="{chart_width - right}" y2="{top + plot_height}" stroke="#9da3ad" />'
        f'<path d="{path}" fill="none" stroke="#c8202f" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" />'
        f'{circles}{labels}</svg></div>'
    )
    st.markdown(chart, unsafe_allow_html=True)
else:
    st.info("Daily workout activity will appear here after the first session is logged.")
st.caption("Dashboard refreshes from the published sheet about every 30 seconds. For a public display, use player nicknames or first name plus last initial and collect parent consent.")
