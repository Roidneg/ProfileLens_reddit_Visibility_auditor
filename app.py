"""Streamlit interface for ProfileLens."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from profilelens.audit import build_audit_report
from profilelens.clients import (
    ArcticShiftClient,
    ConfigurationError,
    DataSourceError,
    RedditCredentials,
    RedditPublicClient,
)
from profilelens.demo import demo_report
from profilelens.exports import report_to_csv, report_to_json
from profilelens.models import AuditReport, AuditStatus
from profilelens.parsing import ProfileInputError, extract_username

load_dotenv()

st.set_page_config(
    page_title="ProfileLens | Reddit Visibility Auditor",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 1240px; padding-top: 2.25rem;}
      [data-testid="stMetric"] {
        background: rgba(25, 35, 55, 0.32);
        border: 1px solid rgba(128, 148, 180, 0.22);
        border-radius: 12px;
        padding: 0.8rem 1rem;
      }
      .method-note {
        border-left: 4px solid #7dd3fc;
        background: rgba(14, 116, 144, 0.12);
        border-radius: 0 8px 8px 0;
        padding: 0.85rem 1rem;
        margin: 0.5rem 0 1rem;
      }
      .small-muted {color: #94a3b8; font-size: 0.9rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False)
def get_archive_client() -> ArcticShiftClient:
    return ArcticShiftClient()


@st.cache_resource(show_spinner=False)
def get_reddit_client(client_id: str, client_secret: str, user_agent: str) -> RedditPublicClient:
    return RedditPublicClient(RedditCredentials(client_id, client_secret, user_agent))


def configured_reddit_credentials() -> RedditCredentials | None:
    values = {
        name: _config_value(name)
        for name in (
            "REDDIT_API_APPROVED",
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "REDDIT_USER_AGENT",
        )
    }
    approved = str(values["REDDIT_API_APPROVED"] or "false").strip().lower()
    if approved not in {"1", "true", "yes"}:
        return None
    required = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    missing = [name for name in required if not str(values[name] or "").strip()]
    if missing:
        raise ConfigurationError(f"Missing configuration: {', '.join(missing)}")
    return RedditCredentials(
        client_id=str(values["REDDIT_CLIENT_ID"]).strip(),
        client_secret=str(values["REDDIT_CLIENT_SECRET"]).strip(),
        user_agent=str(values["REDDIT_USER_AGENT"]).strip(),
    )


def _config_value(name: str):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name)


def run_network_audit(
    profile_input: str,
    *,
    limit: int,
    compare_live: bool,
    max_probes: int,
) -> AuditReport:
    username = extract_username(profile_input)
    archived = get_archive_client().get_user_comments(username, limit=limit)
    public = []
    reddit_client = None
    if compare_live:
        credentials = configured_reddit_credentials()
        if credentials is None:
            raise ConfigurationError(
                "Live comparison requires approved Reddit Data API access and local credentials."
            )
        reddit_client = get_reddit_client(
            credentials.client_id,
            credentials.client_secret,
            credentials.user_agent,
        )
        public = reddit_client.get_profile_comments(username, limit=limit)

    return build_audit_report(
        username,
        archived,
        public,
        public_profile_compared=compare_live,
        requested_public_limit=limit,
        probe=reddit_client.probe_comment if reddit_client else None,
        max_probes=max_probes,
    )


st.title("ProfileLens")
st.subheader("Reddit Profile Visibility Auditor")
st.markdown(
    "Compare a profile's public comment listing with third-party archive records, then "
    "separate what the evidence shows from what it cannot prove."
)
st.markdown(
    '<div class="method-note"><strong>Evidence rule:</strong> profile absence alone is not '
    "proof that a comment was hidden, removed, or deleted. ProfileLens labels each state "
    "according to the sources actually checked.</div>",
    unsafe_allow_html=True,
)

try:
    credentials_ready = configured_reddit_credentials() is not None
    credential_error = ""
except ConfigurationError as exc:
    credentials_ready = False
    credential_error = str(exc)

with st.sidebar:
    st.header("Audit setup")
    mode = st.radio(
        "Mode",
        ("Demonstration", "Archive explorer", "Archive + live comparison"),
        help="Demonstration mode uses fictional data and makes no network calls.",
    )

    profile_input = ""
    limit = 100
    max_probes = 20
    authorized = True
    if mode != "Demonstration":
        profile_input = st.text_input(
            "Reddit profile URL or username",
            placeholder="https://www.reddit.com/user/example/",
        )
        limit = st.select_slider(
            "Comments per source",
            options=(25, 50, 100, 250, 500),
            value=100,
        )
        if mode == "Archive + live comparison":
            max_probes = st.slider(
                "Maximum direct checks",
                min_value=0,
                max_value=50,
                value=20,
                help="Limits additional Reddit API requests for comments absent from the profile listing.",
            )
            if credentials_ready:
                st.success("Approved Reddit API configuration detected.")
            else:
                st.warning(
                    credential_error
                    or "Live comparison is locked until approved Reddit API access is configured."
                )

        authorized = st.checkbox(
            "I own this account or have permission to audit it.",
            value=False,
        )

    include_full_text = st.checkbox(
        "Include full comment text in exports",
        value=False,
        help="Off by default to minimize unnecessary redistribution of archived content.",
    )
    run_disabled = (mode != "Demonstration" and (not profile_input.strip() or not authorized)) or (
        mode == "Archive + live comparison" and not credentials_ready
    )
    run_clicked = st.button("Run audit", type="primary", width="stretch", disabled=run_disabled)

    st.divider()
    st.markdown(
        "**Privacy by design**\n\n"
        "- No application database\n"
        "- No account passwords\n"
        "- Full-text exports are opt-in\n"
        "- Approved API access only"
    )


if run_clicked:
    try:
        if mode == "Demonstration":
            report = demo_report()
        else:
            with st.spinner("Collecting and comparing evidence…"):
                report = run_network_audit(
                    profile_input,
                    limit=limit,
                    compare_live=mode == "Archive + live comparison",
                    max_probes=max_probes,
                )
        st.session_state["audit_report"] = report
        st.session_state["include_full_text"] = include_full_text
    except (ConfigurationError, DataSourceError, ProfileInputError, ValueError) as exc:
        st.error(str(exc))


report = st.session_state.get("audit_report")
if report is None:
    st.info(
        "Choose Demonstration and run the audit to explore the evidence model without credentials."
    )
    st.stop()

st.markdown(f"### Results for `u/{report.username}`")
summary = report.summary
metric_columns = st.columns(4)
metric_columns[0].metric("Archived", report.archive_count)
metric_columns[1].metric("Public listing", report.public_profile_count)
metric_columns[2].metric(
    "Live, not listed",
    summary.get(AuditStatus.LIVE_NOT_LISTED.value, 0),
)
metric_columns[3].metric("Direct checks", report.probes_run)

results_tab, methodology_tab, export_tab = st.tabs(("Evidence table", "Methodology", "Export"))

with results_tab:
    available_statuses = sorted({row.status.value for row in report.rows})
    selected_statuses = st.multiselect(
        "Filter statuses",
        options=available_statuses,
        default=available_statuses,
    )
    table_rows = [
        row.to_dict(include_body=False)
        for row in report.rows
        if row.status.value in selected_statuses
    ]
    frame = pd.DataFrame(table_rows)
    if frame.empty:
        st.warning("No rows match the selected filters.")
    else:
        frame["created_utc"] = pd.to_datetime(frame["created_utc"], utc=True)
        display_columns = [
            "status",
            "confidence",
            "created_utc",
            "subreddit",
            "archive_body",
            "interpretation",
            "permalink",
            "comment_id",
        ]
        st.dataframe(
            frame[display_columns],
            hide_index=True,
            width="stretch",
            column_config={
                "status": st.column_config.TextColumn("Evidence status", width="medium"),
                "confidence": st.column_config.TextColumn("Confidence", width="small"),
                "created_utc": st.column_config.DatetimeColumn(
                    "Created (UTC)", format="YYYY-MM-DD HH:mm"
                ),
                "subreddit": st.column_config.TextColumn("Community", width="small"),
                "archive_body": st.column_config.TextColumn("Archived text preview", width="large"),
                "interpretation": st.column_config.TextColumn("What it means", width="large"),
                "permalink": st.column_config.LinkColumn("Reddit link", display_text="Open"),
                "comment_id": st.column_config.TextColumn("Comment ID", width="small"),
            },
        )

    if report.public_limit_reached:
        st.warning(
            "The public listing hit the requested limit. Older archived comments were marked "
            "outside the comparison window rather than treated as hidden."
        )

with methodology_tab:
    st.markdown(
        """
        #### Classification logic

        - **Visible on public profile:** the same comment ID appears in both sources.
        - **Live but not listed:** the archive contains it, the profile listing does not, and a direct Reddit lookup still returns it.
        - **Removed or deleted:** Reddit returns its corresponding marker during a direct lookup.
        - **Archive only:** an archive record exists, but Reddit does not currently return enough evidence to determine why.
        - **Outside comparison window:** the archive record is older than the oldest item in a capped public listing.

        #### What the report does not prove

        Archive coverage can be incomplete. A missing profile entry can result from curation, deletion,
        moderation, listing limits, account state, API behavior, or a transient source failure. Use a
        controlled before-and-after test when making a claim about profile curation.
        """
    )
    st.markdown("#### Run metadata")
    st.json(report.to_dict(include_body=False)["metadata"], expanded=False)

with export_tab:
    export_full_text = st.checkbox(
        "Include full text in these downloads",
        value=bool(st.session_state.get("include_full_text", False)),
        key="download_full_text",
    )
    if export_full_text:
        st.warning("The export will include complete archived comment bodies. Share it carefully.")
    csv_bytes = report_to_csv(report, include_body=export_full_text)
    json_bytes = report_to_json(report, include_body=export_full_text)
    safe_name = report.username.lower().replace("-", "_")
    download_columns = st.columns(2)
    download_columns[0].download_button(
        "Download CSV",
        data=csv_bytes,
        file_name=f"profilelens_{safe_name}.csv",
        mime="text/csv",
        width="stretch",
    )
    download_columns[1].download_button(
        "Download JSON",
        data=json_bytes,
        file_name=f"profilelens_{safe_name}.json",
        mime="application/json",
        width="stretch",
    )

st.caption(
    "ProfileLens is an independent portfolio project. It is not affiliated with Reddit or Arctic Shift. "
    "Use it only for authorized, lawful, and non-harassing analysis."
)
