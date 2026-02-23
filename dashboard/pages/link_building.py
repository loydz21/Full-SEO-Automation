"""Link Building — Streamlit Dashboard Page.

Tabs: Find Prospects, Outreach, Backlink Monitor,
Competitor Analysis, Toxic Links, Stats, Export.
"""

import asyncio
import json
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.database import get_session, init_db
from src.integrations.llm_client import LLMClient
from src.integrations.serp_scraper import SERPScraper
from src.models.backlink import (
    Backlink,
    BacklinkCheck,
    EmailTemplate,
    OutreachCampaign,
    OutreachEmail,
    OutreachProspect,
)
from src.modules.link_building.backlink_monitor import BacklinkMonitor
from src.modules.link_building.outreach import OutreachManager
from src.modules.link_building.prospector import LinkProspector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine from synchronous Streamlit code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _score_badge(score: Optional[float]) -> str:
    """Return coloured score display."""
    if score is None:
        return "—"
    pct = int(score * 100)
    if pct >= 70:
        colour = "green"
    elif pct >= 40:
        colour = "orange"
    else:
        colour = "red"
    return f'<span style="color:{colour};font-weight:bold;">{pct}%</span>'


def _status_badge(status: str) -> str:
    """Return a coloured badge for outreach status."""
    colours = {
        "new": "#6b7280",
        "sent": "#3b82f6",
        "opened": "#8b5cf6",
        "replied": "#f59e0b",
        "accepted": "#16a34a",
        "rejected": "#ef4444",
        "active": "#16a34a",
        "lost_404": "#ef4444",
        "lost_removed": "#ef4444",
        "lost_error": "#ef4444",
    }
    bg = colours.get(status, "#6b7280")
    return (
        f'<span style="background:{bg};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;">{status.upper()}</span>'
    )


def _ensure_db():
    """Make sure tables exist."""
    try:
        init_db()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_link_building_page():
    """Render the Link Building dashboard page."""
    st.title("🔗 Link Building")
    st.markdown("Discover prospects, manage outreach, and monitor backlinks.")

    _ensure_db()

    tabs = st.tabs([
        "🔍 Find Prospects",
        "📧 Outreach",
        "📊 Backlink Monitor",
        "🏆 Competitor Analysis",
        "☠️ Toxic Links",
        "📈 Stats",
        "📥 Export",
    ])

    with tabs[0]:
        _render_prospects_tab()
    with tabs[1]:
        _render_outreach_tab()
    with tabs[2]:
        _render_monitor_tab()
    with tabs[3]:
        _render_competitor_tab()
    with tabs[4]:
        _render_toxic_tab()
    with tabs[5]:
        _render_stats_tab()
    with tabs[6]:
        _render_export_tab()


# ---------------------------------------------------------------------------
# Tab 1: Find Prospects
# ---------------------------------------------------------------------------

def _render_prospects_tab():
    st.subheader("🔍 Find Link Building Prospects")

    col1, col2 = st.columns(2)
    with col1:
        domain = st.text_input("Your Domain", placeholder="example.com", key="lp_domain")
        keywords_raw = st.text_area(
            "Keywords (one per line)",
            placeholder="seo tools\ndigital marketing\ncontent strategy",
            height=120,
            key="lp_keywords",
        )
    with col2:
        st.markdown("**Select Strategies**")
        strat_guest = st.checkbox("Guest Post Opportunities", value=True, key="lp_s_guest")
        strat_resource = st.checkbox("Resource Page Links", value=True, key="lp_s_resource")
        strat_broken = st.checkbox("Broken Link Building", value=False, key="lp_s_broken")
        strat_competitor = st.checkbox("Competitor Backlinks", value=False, key="lp_s_comp")
        strat_mentions = st.checkbox("Unlinked Mentions", value=False, key="lp_s_mentions")

    strategies = []
    if strat_guest:
        strategies.append("guest_post")
    if strat_resource:
        strategies.append("resource_page")
    if strat_broken:
        strategies.append("broken_link")
    if strat_competitor:
        strategies.append("competitor_backlinks")
    if strat_mentions:
        strategies.append("unlinked_mentions")

    col_a, col_b = st.columns(2)
    with col_a:
        find_btn = st.button("🔍 Find Prospects", type="primary", use_container_width=True)
    with col_b:
        save_btn = st.button(
            "💾 Save Results to DB", use_container_width=True,
            disabled="lp_results" not in st.session_state,
        )

    if find_btn and domain and keywords_raw.strip() and strategies:
        keywords = [k.strip() for k in keywords_raw.strip().splitlines() if k.strip()]
        with st.spinner("Searching for prospects... This may take a few minutes."):
            try:
                prospector = LinkProspector()
                results = _run_async(
                    prospector.find_prospects(domain, keywords, strategies)
                )
                st.session_state["lp_results"] = results
                st.success("Found " + str(len(results)) + " prospects!")
            except Exception as exc:
                st.error("Prospect search failed: " + str(exc))
                st.expander("Error details").code(traceback.format_exc())

    if save_btn and "lp_results" in st.session_state:
        prospector = LinkProspector()
        ids = prospector.save_prospects_to_db(st.session_state["lp_results"])
        st.success("Saved " + str(len(ids)) + " prospects to database!")

    # Display results
    if "lp_results" in st.session_state and st.session_state["lp_results"]:
        results = st.session_state["lp_results"]
        st.markdown("---")
        st.markdown("### Results (" + str(len(results)) + " prospects)")

        # Filter controls
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            all_strategies = list(set(r.get("strategy_type", "") for r in results))
            strat_filter = st.multiselect(
                "Filter by Strategy", all_strategies, default=all_strategies, key="lp_filter"
            )
        with filter_col2:
            min_score = st.slider("Minimum Score", 0.0, 1.0, 0.0, 0.05, key="lp_min_score")

        filtered = [
            r for r in results
            if r.get("strategy_type", "") in strat_filter
            and (r.get("relevance_score") or 0) >= min_score
        ]

        if filtered:
            df_data = []
            for r in filtered:
                df_data.append({
                    "Domain": r.get("domain", ""),
                    "Title": (r.get("title", "") or "")[:60],
                    "Strategy": r.get("strategy_type", ""),
                    "Score": round(r.get("relevance_score", 0) * 100),
                    "URL": r.get("url", ""),
                })
            df = pd.DataFrame(df_data)
            st.dataframe(
                df.sort_values("Score", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No prospects match current filters.")

    # Show saved prospects from DB
    st.markdown("---")
    with st.expander("📂 Saved Prospects from Database"):
        prospector = LinkProspector()
        saved = prospector.get_saved_prospects()
        if saved:
            df_saved = pd.DataFrame(saved)
            cols_show = ["id", "domain", "strategy_type", "relevance_score", "status", "contact_email"]
            available_cols = [c for c in cols_show if c in df_saved.columns]
            st.dataframe(df_saved[available_cols], use_container_width=True, hide_index=True)
        else:
            st.info("No saved prospects yet.")


# ---------------------------------------------------------------------------
# Tab 2: Outreach
# ---------------------------------------------------------------------------

def _render_outreach_tab():
    st.subheader("📧 Outreach Management")

    # Business info for email generation
    with st.expander("⚙️ Business Info (for email personalisation)", expanded=False):
        biz_col1, biz_col2 = st.columns(2)
        with biz_col1:
            biz_name = st.text_input("Your Name", key="or_biz_name", value="SEO Professional")
            biz_site = st.text_input("Your Website", key="or_biz_site", placeholder="https://mysite.com")
        with biz_col2:
            biz_topic = st.text_input("Your Niche/Topic", key="or_biz_topic", placeholder="Digital Marketing")
            biz_creds = st.text_input("Credentials", key="or_biz_creds", placeholder="Published on Moz, SEJ...")

    business_info = {
        "name": biz_name,
        "site": biz_site,
        "topic": biz_topic,
        "credentials": biz_creds,
    }

    # Load prospects
    prospector = LinkProspector()
    prospects = prospector.get_saved_prospects()

    if not prospects:
        st.info("No prospects found. Use the Find Prospects tab first.")
        return

    # Prospect selector
    prospect_options = {
        str(p["id"]) + " - " + p["domain"]: p for p in prospects
    }
    selected_key = st.selectbox(
        "Select Prospect", list(prospect_options.keys()), key="or_prospect_sel"
    )
    selected_prospect = prospect_options.get(selected_key, {})

    if selected_prospect:
        info_col1, info_col2, info_col3 = st.columns(3)
        with info_col1:
            st.metric("Domain", selected_prospect.get("domain", ""))
        with info_col2:
            st.metric("Strategy", selected_prospect.get("strategy_type", ""))
        with info_col3:
            st.metric("Status", selected_prospect.get("status", "new"))

    gen_col1, gen_col2 = st.columns(2)
    with gen_col1:
        template_type = st.selectbox(
            "Email Type",
            ["guest_post", "resource_link", "broken_link", "collaboration", "testimonial"],
            key="or_template_type",
        )
        gen_single = st.button("✉️ Generate Email", type="primary", use_container_width=True)
    with gen_col2:
        gen_sequence = st.button(
            "📬 Generate 3-Email Sequence", use_container_width=True
        )

    # Generate single email
    if gen_single and selected_prospect:
        with st.spinner("Generating personalised email..."):
            try:
                manager = OutreachManager()
                email = _run_async(
                    manager.generate_outreach_email(
                        selected_prospect, template_type, business_info
                    )
                )
                st.session_state["or_generated_email"] = email
            except Exception as exc:
                st.error("Email generation failed: " + str(exc))

    # Generate sequence
    if gen_sequence and selected_prospect:
        with st.spinner("Generating email sequence..."):
            try:
                manager = OutreachManager()
                sequence = _run_async(
                    manager.generate_email_sequence(selected_prospect, business_info)
                )
                st.session_state["or_generated_sequence"] = sequence
            except Exception as exc:
                st.error("Sequence generation failed: " + str(exc))

    # Display generated email
    if "or_generated_email" in st.session_state:
        email = st.session_state["or_generated_email"]
        st.markdown("---")
        st.markdown("### ✉️ Generated Email")
        st.text_input("Subject", value=email.get("subject", ""), key="or_email_subject")
        st.text_area("Body", value=email.get("body", ""), height=200, key="or_email_body")
        if email.get("follow_up_body"):
            with st.expander("Follow-up Email"):
                st.text_area(
                    "Follow-up Body", value=email["follow_up_body"],
                    height=150, key="or_email_followup",
                )

        save_col1, save_col2 = st.columns(2)
        with save_col1:
            if st.button("💾 Save Email to DB", use_container_width=True):
                manager = OutreachManager()
                eid = manager.save_email_to_db(
                    prospect_id=selected_prospect["id"],
                    subject=email.get("subject", ""),
                    body=email.get("body", ""),
                )
                st.success("Email saved (ID: " + str(eid) + ")")
        with save_col2:
            if st.button("📋 Mark as Sent", use_container_width=True):
                manager = OutreachManager()
                manager.track_outreach(selected_prospect["id"], "sent")
                st.success("Prospect marked as sent!")

    # Display generated sequence
    if "or_generated_sequence" in st.session_state:
        sequence = st.session_state["or_generated_sequence"]
        st.markdown("---")
        st.markdown("### 📬 Email Sequence")
        for i, email in enumerate(sequence):
            seq_num = email.get("sequence_number", i + 1)
            delay = email.get("send_delay_days", 0)
            label = "Email " + str(seq_num)
            if delay > 0:
                label = label + " (Day +" + str(delay) + ")"
            with st.expander(label):
                st.text_input(
                    "Subject", value=email.get("subject", ""),
                    key="or_seq_subj_" + str(i),
                )
                st.text_area(
                    "Body", value=email.get("body", ""),
                    height=150, key="or_seq_body_" + str(i),
                )

    # Outreach status tracking
    st.markdown("---")
    st.markdown("### 📋 Update Outreach Status")
    track_col1, track_col2, track_col3 = st.columns(3)
    with track_col1:
        track_prospect_id = st.number_input(
            "Prospect ID", min_value=1, step=1, key="or_track_id"
        )
    with track_col2:
        new_status = st.selectbox(
            "New Status",
            ["sent", "opened", "replied", "accepted", "rejected"],
            key="or_track_status",
        )
    with track_col3:
        track_notes = st.text_input("Notes", key="or_track_notes")

    if st.button("Update Status", key="or_track_btn"):
        try:
            manager = OutreachManager()
            result = manager.track_outreach(int(track_prospect_id), new_status, track_notes)
            st.success(
                "Updated prospect " + str(result["id"]) + ": "
                + result["old_status"] + " → " + result["new_status"]
            )
        except Exception as exc:
            st.error("Update failed: " + str(exc))


# ---------------------------------------------------------------------------
# Tab 3: Backlink Monitor
# ---------------------------------------------------------------------------

def _render_monitor_tab():
    st.subheader("📊 Backlink Monitor")

    monitor = BacklinkMonitor()

    # Summary metrics
    all_backlinks = monitor.get_all_backlinks()
    total = len(all_backlinks)
    active = sum(1 for b in all_backlinks if b["status"] == "active")
    lost = sum(1 for b in all_backlinks if b["status"].startswith("lost"))
    dofollow = sum(1 for b in all_backlinks if b["dofollow"])

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Backlinks", total)
    with m2:
        st.metric("Active", active)
    with m3:
        st.metric("Lost", lost)
    with m4:
        dofollow_pct = str(round(dofollow / total * 100)) + "%" if total else "—"
        st.metric("Dofollow Ratio", dofollow_pct)

    st.markdown("---")

    # Add new backlink
    with st.expander("➕ Add Backlink for Monitoring"):
        add_col1, add_col2 = st.columns(2)
        with add_col1:
            add_source = st.text_input("Source URL", key="bm_add_source")
            add_domain = st.text_input("Source Domain", key="bm_add_domain")
        with add_col2:
            add_target = st.text_input("Target URL (your page)", key="bm_add_target")
            add_anchor = st.text_input("Anchor Text", key="bm_add_anchor")
            add_type = st.selectbox(
                "Link Type", ["dofollow", "nofollow", "sponsored", "ugc"],
                key="bm_add_type",
            )

        if st.button("Add Backlink", key="bm_add_btn"):
            if add_source and add_domain:
                result = monitor.add_backlink(
                    url=add_source,
                    source_domain=add_domain,
                    anchor_text=add_anchor,
                    link_type=add_type,
                    target_url=add_target,
                )
                st.success("Backlink added (ID: " + str(result["id"]) + ")")
                st.rerun()
            else:
                st.warning("Source URL and Domain are required.")

    # Check backlinks
    check_col1, check_col2 = st.columns(2)
    with check_col1:
        check_domain = st.text_input("Domain to Check", key="bm_check_domain")
    with check_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        check_btn = st.button("🔄 Check All Backlinks", type="primary", use_container_width=True)

    if check_btn and check_domain:
        with st.spinner("Checking backlinks... This may take a while."):
            try:
                report = _run_async(monitor.check_backlinks(check_domain))
                st.session_state["bm_check_report"] = report
                st.success(
                    "Check complete: " + str(report["alive"]) + " alive, "
                    + str(report["lost"]) + " lost, "
                    + str(report["changed"]) + " changed"
                )
            except Exception as exc:
                st.error("Check failed: " + str(exc))

    if "bm_check_report" in st.session_state:
        report = st.session_state["bm_check_report"]
        if report.get("changes"):
            st.markdown("#### ⚠️ Changes Detected")
            for change in report["changes"]:
                st.warning(
                    "Backlink " + str(change["backlink_id"]) + " ("
                    + change["source_url"][:60] + "): "
                    + change["change_type"] + " — "
                    + str(change["old_value"]) + " → " + str(change["new_value"])
                )

    # Backlink table
    if all_backlinks:
        st.markdown("#### 📋 All Backlinks")
        df_data = []
        for b in all_backlinks:
            df_data.append({
                "ID": b["id"],
                "Source Domain": b["source_domain"],
                "Anchor Text": (b["anchor_text"] or "")[:40],
                "Type": b["link_type"],
                "Status": b["status"],
                "DA": b["domain_authority"] or "—",
                "Toxic": "⚠️" if b["is_toxic"] else "✅",
                "Last Checked": (b["last_checked"] or "Never")[:19],
            })
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Tab 4: Competitor Analysis
# ---------------------------------------------------------------------------

def _render_competitor_tab():
    st.subheader("🏆 Competitor Backlink Analysis")

    comp_domains_raw = st.text_area(
        "Competitor Domains (one per line)",
        placeholder="competitor1.com\ncompetitor2.com",
        height=100,
        key="ca_domains",
    )

    if st.button("🔍 Analyze Competitors", type="primary"):
        domains = [d.strip() for d in comp_domains_raw.strip().splitlines() if d.strip()]
        if not domains:
            st.warning("Enter at least one competitor domain.")
            return

        all_results = []
        progress = st.progress(0)
        for i, comp_domain in enumerate(domains):
            with st.spinner("Analyzing " + comp_domain + "..."):
                try:
                    prospector = LinkProspector()
                    results = _run_async(
                        prospector.find_competitor_backlinks(comp_domain)
                    )
                    for r in results:
                        r["competitor"] = comp_domain
                    all_results.extend(results)
                except Exception as exc:
                    st.warning("Failed to analyze " + comp_domain + ": " + str(exc))
            progress.progress((i + 1) / len(domains))

        st.session_state["ca_results"] = all_results
        st.success("Found " + str(len(all_results)) + " linking sites across competitors!")

    if "ca_results" in st.session_state and st.session_state["ca_results"]:
        results = st.session_state["ca_results"]
        df_data = []
        for r in results:
            df_data.append({
                "Domain": r.get("domain", ""),
                "Competitor": r.get("competitor", ""),
                "Title": (r.get("title", "") or "")[:50],
                "Score": round(r.get("relevance_score", 0) * 100),
                "URL": r.get("url", ""),
            })
        df = pd.DataFrame(df_data)
        st.dataframe(
            df.sort_values("Score", ascending=False),
            use_container_width=True, hide_index=True,
        )

        if st.button("💾 Save Competitor Prospects", key="ca_save"):
            prospector = LinkProspector()
            ids = prospector.save_prospects_to_db(results)
            st.success("Saved " + str(len(ids)) + " competitor prospects!")


# ---------------------------------------------------------------------------
# Tab 5: Toxic Links
# ---------------------------------------------------------------------------

def _render_toxic_tab():
    st.subheader("☠️ Toxic Link Detection")

    monitor = BacklinkMonitor()

    toxic_col1, toxic_col2 = st.columns(2)
    with toxic_col1:
        toxic_domain = st.text_input("Domain to Scan", key="tl_domain")
    with toxic_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        scan_btn = st.button(
            "🔍 Scan for Toxic Links", type="primary", use_container_width=True
        )

    if scan_btn and toxic_domain:
        with st.spinner("Scanning for toxic links..."):
            try:
                backlinks = monitor.get_all_backlinks(domain=toxic_domain)
                if not backlinks:
                    st.warning("No backlinks found for this domain. Add backlinks first.")
                    return
                toxic = _run_async(monitor.detect_toxic_links(backlinks))
                st.session_state["tl_results"] = toxic
                st.session_state["tl_total"] = len(backlinks)

                if toxic:
                    st.error("Found " + str(len(toxic)) + " toxic links out of " + str(len(backlinks)) + "!")
                else:
                    st.success("No toxic links detected! Your profile looks clean.")
            except Exception as exc:
                st.error("Toxic scan failed: " + str(exc))

    if "tl_results" in st.session_state and st.session_state["tl_results"]:
        toxic = st.session_state["tl_results"]

        df_data = []
        for t in toxic:
            df_data.append({
                "ID": t.get("id", ""),
                "Source Domain": t.get("source_domain", ""),
                "Anchor Text": (t.get("anchor_text", "") or "")[:40],
                "Reason": t.get("toxic_reason", ""),
                "Severity": t.get("toxic_severity", "medium"),
            })
        df = pd.DataFrame(df_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Disavow file generation
        st.markdown("---")
        st.markdown("#### 📄 Generate Disavow File")
        if st.button("Generate Google Disavow File", key="tl_disavow"):
            disavow_content = monitor.generate_disavow_file(toxic)
            st.session_state["tl_disavow_content"] = disavow_content

        if "tl_disavow_content" in st.session_state:
            content = st.session_state["tl_disavow_content"]
            st.code(content, language="text")
            st.download_button(
                "⬇️ Download Disavow File",
                data=content,
                file_name="disavow.txt",
                mime="text/plain",
            )


# ---------------------------------------------------------------------------
# Tab 6: Stats
# ---------------------------------------------------------------------------

def _render_stats_tab():
    st.subheader("📈 Outreach Statistics")

    manager = OutreachManager()
    stats = manager.get_outreach_stats()

    # Top-level metrics
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric("Total Prospects", stats["total_prospects"])
    with s2:
        st.metric("Emails Sent", stats["total_sent"])
    with s3:
        rate_str = str(stats["response_rate"]) + "%"
        st.metric("Response Rate", rate_str)
    with s4:
        acc_str = str(stats["acceptance_rate"]) + "%"
        st.metric("Acceptance Rate", acc_str)

    st.markdown("---")

    # Status breakdown
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("#### Status Breakdown")
        by_status = stats.get("by_status", {})
        if by_status:
            df_status = pd.DataFrame(
                [{"Status": k, "Count": v} for k, v in by_status.items()]
            )
            st.bar_chart(df_status.set_index("Status"))
        else:
            st.info("No outreach data yet.")

    with col_right:
        st.markdown("#### By Strategy")
        by_strategy = stats.get("by_strategy", {})
        if by_strategy:
            strat_rows = []
            for strat_name, strat_data in by_strategy.items():
                strat_rows.append({
                    "Strategy": strat_name,
                    "Total": strat_data.get("total", 0),
                    "Sent": strat_data.get("sent", 0),
                    "Replied": strat_data.get("replied", 0),
                    "Accepted": strat_data.get("accepted", 0),
                })
            df_strat = pd.DataFrame(strat_rows)
            st.dataframe(df_strat, use_container_width=True, hide_index=True)
        else:
            st.info("No strategy data yet.")

    # Funnel visualization
    st.markdown("---")
    st.markdown("#### 🔄 Outreach Funnel")
    funnel_data = {
        "Prospects": stats["total_prospects"],
        "Sent": stats["total_sent"],
        "Replied": stats["total_replied"],
        "Accepted": stats["total_accepted"],
    }
    if any(v > 0 for v in funnel_data.values()):
        df_funnel = pd.DataFrame(
            [{"Stage": k, "Count": v} for k, v in funnel_data.items()]
        )
        st.bar_chart(df_funnel.set_index("Stage"))
    else:
        st.info("Start outreach to see funnel data.")


# ---------------------------------------------------------------------------
# Tab 7: Export
# ---------------------------------------------------------------------------

def _render_export_tab():
    st.subheader("📥 Export Data")
    # --- PDF Report Download ---
    st.markdown("**📄 Professional PDF Report**")
    st.markdown("Generate a narrative PDF report with backlink analysis and charts.")
    if st.button("Generate PDF Report", type="primary", key="lb_pdf_btn"):
        try:
            from dashboard.export_helper import generate_link_building_pdf
            lb_data = {
                "domain": st.session_state.get("lb_domain", ""),
                "prospects": st.session_state.get("lb_prospects", []),
                "backlinks": st.session_state.get("lb_backlinks", []),
                "outreach_stats": st.session_state.get("lb_outreach_stats", {}),
                "toxic_links": st.session_state.get("lb_toxic_links", []),
            }
            pdf_path = generate_link_building_pdf(lb_data)
            with open(pdf_path, "rb") as fh:
                st.download_button("⬇️ Download PDF", fh.read(),
                    file_name=pdf_path.split("/")[-1], mime="application/pdf", key="lb_pdf_dl")
            st.success("PDF report generated!")
        except Exception as exc:
            st.error("PDF generation failed: " + str(exc))
    st.divider()

    export_type = st.selectbox(
        "Export Type",
        ["Prospects CSV", "Backlinks JSON", "Outreach CSV"],
        key="ex_type",
    )

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        ex_status = st.text_input("Filter by Status (optional)", key="ex_status")
    with filter_col2:
        ex_strategy = st.text_input("Filter by Strategy (optional)", key="ex_strategy")

    if st.button("📦 Generate Export", type="primary"):
        filters = {}
        if ex_status:
            filters["status"] = ex_status
        if ex_strategy:
            filters["strategy_type"] = ex_strategy

        try:
            if export_type == "Prospects CSV":
                manager = OutreachManager()
                csv_data = manager.export_outreach_csv(filters if filters else None)
                st.download_button(
                    "⬇️ Download CSV",
                    data=csv_data,
                    file_name="prospects_export.csv",
                    mime="text/csv",
                )
                st.success("CSV ready for download!")

            elif export_type == "Backlinks JSON":
                monitor = BacklinkMonitor()
                backlinks = monitor.get_all_backlinks(
                    status=filters.get("status"),
                )
                json_data = json.dumps(backlinks, indent=2, default=str)
                st.download_button(
                    "⬇️ Download JSON",
                    data=json_data,
                    file_name="backlinks_export.json",
                    mime="application/json",
                )
                st.success("JSON ready for download!")

            elif export_type == "Outreach CSV":
                manager = OutreachManager()
                csv_data = manager.export_outreach_csv(filters if filters else None)
                st.download_button(
                    "⬇️ Download CSV",
                    data=csv_data,
                    file_name="outreach_export.csv",
                    mime="text/csv",
                )
                st.success("CSV ready for download!")

        except Exception as exc:
            st.error("Export failed: " + str(exc))
            st.expander("Error details").code(traceback.format_exc())

    # Quick preview
    st.markdown("---")
    with st.expander("👁️ Preview Data"):
        preview_type = st.radio(
            "Preview", ["Prospects", "Backlinks"], horizontal=True, key="ex_preview"
        )
        if preview_type == "Prospects":
            prospector = LinkProspector()
            data = prospector.get_saved_prospects()
            if data:
                st.dataframe(pd.DataFrame(data).head(20), use_container_width=True, hide_index=True)
            else:
                st.info("No prospects in database.")
        else:
            monitor = BacklinkMonitor()
            data = monitor.get_all_backlinks()
            if data:
                st.dataframe(pd.DataFrame(data).head(20), use_container_width=True, hide_index=True)
            else:
                st.info("No backlinks in database.")
