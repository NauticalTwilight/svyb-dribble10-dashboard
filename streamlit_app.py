import os
import re
from datetime import date

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


def _yes(value) -> bool:
    return str(value).strip().lower() in {"yes", "y", "true", "1", "approved", "checked"}


def _grade(value) -> str:
    raw = str(value).strip().lower()
    match = re.search(r"([1-6])", raw)
    if match:
        return f"{match.group(1)}{['th', 'st', 'nd', 'rd', 'th', 'th', 'th'][int(match.group(1))]} Grade"
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
    selected = {}
    for key in COLUMN_ALIASES:
        selected[key] = _find_column(raw.columns, key)
    required = ["grade", "session_date", "minutes", "parent_confirmed", "show_public"]
    missing = [key for key in required if selected[key] is None]
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"The Dashboard Feed is missing required column(s): {names}.")

    data = pd.DataFrame()
    for key, column in selected.items():
        data[key] = raw[column] if column is not None else ""

    data["grade"] = data["grade"].map(_grade)
    data["session_date"] = pd.to_datetime(data["session_date"], errors="coerce").dt.date
    data["minutes"] = pd.to_numeric(data["minutes"], errors="coerce").fillna(0)
    data["parent_confirmed"] = data["parent_confirmed"].map(_yes)
    data["show_public"] = data["show_public"].map(_yes)
    data["display_name"] = data["display_name"].fillna("").astype(str).str.strip()
    # Forms may return values such as "1 (Sep 28 - Oct 4)" rather than "Week 1".
    data["week"] = data["week"].fillna("").map(_week)

    # Count only parent-confirmed, full 10-minute sessions with a supported grade and valid date.
    data = data[
        data["parent_confirmed"]
        & (data["minutes"] >= 10)
        & data["session_date"].notna()
        & data["grade"].isin(GRADE_ORDER)
    ].copy()
    data["sessions"] = 1
    return data


@st.cache_data(ttl=30, show_spinner=False)
def load_csv(url: str) -> pd.DataFrame:
    return pd.read_csv(url)


st.title("🏀 SVYB Dribble 10")
st.caption("A community challenge to build confidence, consistency, and better ball handling—10 minutes at a time.")

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

if data.empty:
    st.info("No confirmed 10-minute workouts have been reported yet. Be the first to log one!")
    st.stop()

# Every accepted submission counts toward community and grade totals. Only opted-in display names
# appear in individual leaderboards or daily player lists.
public_data = data[data["show_public"] & data["display_name"].ne("")].copy()
challenge_start = st.secrets.get("challenge_start", os.getenv("CHALLENGE_START", "")).strip()
challenge_end = st.secrets.get("challenge_end", os.getenv("CHALLENGE_END", "")).strip()
if challenge_start:
    start = pd.to_datetime(challenge_start, errors="coerce")
    if not pd.isna(start):
        data = data[data["session_date"] >= start.date()]
        public_data = public_data[public_data["session_date"] >= start.date()]
if challenge_end:
    end = pd.to_datetime(challenge_end, errors="coerce")
    if not pd.isna(end):
        data = data[data["session_date"] <= end.date()]
        public_data = public_data[public_data["session_date"] <= end.date()]

sessions = len(data)
minutes = int(data["minutes"].sum())
public_players = public_data[["grade", "display_name"]].drop_duplicates().shape[0]

m1, m2, m3 = st.columns(3)
m1.metric("Confirmed 10-minute workouts", f"{sessions:,}")
m2.metric("Dribbling minutes", f"{minutes:,}")
m3.metric("Players on the public leaderboard", f"{public_players:,}")
st.caption("Grade totals include all parent-confirmed sessions. Individual names and daily check-ins appear only when a family opts in to public display.")

st.subheader("Workouts by grade")
grade_totals = (data.groupby("grade").size().reindex(GRADE_ORDER, fill_value=0).rename("Workouts").to_frame())
st.bar_chart(grade_totals, y="Workouts", color="#c8202f")

st.subheader("Grade leaderboards")
selected_grade = st.selectbox("Choose a grade", GRADE_ORDER)
grade_public = public_data[public_data["grade"] == selected_grade].copy()
grade_all = data[data["grade"] == selected_grade]
private_sessions = len(grade_all) - len(grade_public)
if private_sessions:
    st.caption(f"{private_sessions} workout(s) in this grade count toward the total but are not listed by player because the family did not opt in to public display.")

if grade_public.empty:
    st.info("No families in this grade have opted in to the public leaderboard yet. Their confirmed sessions still count toward the grade total above.")
else:
    grouped = (grade_public.groupby("display_name")
               .agg(Total=("sessions", "sum"), Latest=("session_date", "max"))
               .sort_values(["Total", "Latest",], ascending=[False, False]))
    week_counts = (grade_public.pivot_table(index="display_name", columns="week", values="sessions", aggfunc="sum", fill_value=0))
    for week in ["Week 1", "Week 2", "Week 3"]:
        if week not in week_counts.columns:
            week_counts[week] = 0
    week_counts = week_counts[["Week 1", "Week 2", "Week 3"]]
    grouped = grouped.join(week_counts).reset_index().rename(columns={"display_name": "Player", "Latest": "Last workout"})
    grouped.insert(0, "Rank", range(1, len(grouped) + 1))
    grouped["Last workout"] = grouped["Last workout"].map(lambda d: d.strftime("%b %-d") if hasattr(d, "strftime") else str(d))
    st.dataframe(grouped, hide_index=True, use_container_width=True)

    with st.expander(f"Daily check-ins — {selected_grade}"):
        daily = grade_public.sort_values(["session_date", "display_name"], ascending=[False, True]).copy()
        daily["Date"] = daily["session_date"].map(lambda d: d.strftime("%b %-d, %Y"))
        daily = daily[["Date", "display_name", "week"]].rename(columns={"display_name": "Player", "week": "Challenge week"})
        daily = daily.drop_duplicates(subset=["Date", "Player"])
        st.dataframe(daily, hide_index=True, use_container_width=True)

st.subheader("Daily community activity")
daily_counts = data.groupby("session_date").size().sort_index().rename("Workouts")
daily_counts.index = daily_counts.index.map(lambda d: d.strftime("%b %-d"))
st.line_chart(daily_counts, color="#c8202f")
st.caption("Updates about every 30 seconds. A newly submitted Google Form response may take a short time to appear in the published sheet.")
