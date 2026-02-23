"""Settings & API Keys Management Page.

Provides a UI for managing all API keys, testing connections,
and configuring application settings.
"""

import streamlit as st
import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.env_manager import EnvManager


def get_manager() -> EnvManager:
    """Get EnvManager instance."""
    env_path = project_root / ".env"
    return EnvManager(str(env_path))


def test_openai_key(api_key: str) -> tuple[bool, str]:
    """Test OpenAI API key validity."""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say OK"}],
            max_tokens=5,
        )
        return True, f"Connected! Model: gpt-4o-mini"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def test_gemini_key(api_key: str) -> tuple[bool, str]:
    """Test Google Gemini API key."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Say OK")
        return True, f"Connected! Model: gemini-2.0-flash"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def test_pagespeed_key(api_key: str) -> tuple[bool, str]:
    """Test PageSpeed Insights API key."""
    try:
        import requests
        url = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        params = {"url": "https://www.google.com", "key": api_key, "strategy": "mobile"}
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return True, "Connected! API key valid."
        return False, f"HTTP {resp.status_code}: {resp.text[:80]}"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def test_serpapi_key(api_key: str) -> tuple[bool, str]:
    """Test SerpAPI key."""
    try:
        import requests
        url = "https://serpapi.com/account.json"
        resp = requests.get(url, params={"api_key": api_key}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            remaining = data.get("total_searches_left", "?")
            return True, f"Connected! Searches remaining: {remaining}"
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


def test_smtp_connection(host: str, port: str, username: str, password: str) -> tuple[bool, str]:
    """Test SMTP connection."""
    try:
        import smtplib
        server = smtplib.SMTP(host, int(port), timeout=10)
        server.starttls()
        server.login(username, password)
        server.quit()
        return True, "Connected! SMTP login successful."
    except Exception as e:
        return False, f"Error: {str(e)[:100]}"


TEST_FUNCTIONS = {
    "OPENAI_API_KEY": lambda v: test_openai_key(v),
    "GOOGLE_GEMINI_API_KEY": lambda v: test_gemini_key(v),
    "PAGESPEED_API_KEY": lambda v: test_pagespeed_key(v),
    "SERPAPI_KEY": lambda v: test_serpapi_key(v),
}


def render_settings_page():
    """Render the Settings & API Keys page."""

    # Header
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3a5f, #2563eb); padding: 24px 30px;
                border-radius: 14px; margin-bottom: 24px;">
        <h1 style="color: white; margin: 0;">⚙️ Settings & API Keys</h1>
        <p style="color: rgba(255,255,255,0.8); margin: 6px 0 0 0;">
            Configure your API keys, test connections, and manage application settings.
        </p>
    </div>
    """, unsafe_allow_html=True)

    manager = get_manager()
    manager.ensure_env_exists()
    env_vars = manager.load_env()
    status = manager.get_status()

    # Summary bar
    total_keys = len(manager.API_KEY_REGISTRY)
    configured = sum(1 for s in status.values() if s.get("configured"))
    required_keys = [k for k, m in manager.API_KEY_REGISTRY.items() if m.get("required")]
    required_configured = sum(1 for k in required_keys if status.get(k, {}).get("configured"))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🔑 Total Keys", f"{configured}/{total_keys}")
    with c2:
        st.metric("🔴 Required", f"{required_configured}/{len(required_keys)}")
    with c3:
        optional_configured = configured - required_configured
        optional_total = total_keys - len(required_keys)
        st.metric("🟡 Optional", f"{optional_configured}/{optional_total}")
    with c4:
        budget = env_vars.get("MONTHLY_BUDGET_LIMIT", "100")
        st.metric("💰 Budget Limit", f"${budget}/mo")

    st.markdown("---")

    # Initialize form values in session state
    if "settings_values" not in st.session_state:
        st.session_state.settings_values = dict(env_vars)

    # Group by category
    categories = manager.get_categories()
    cat_keys: dict[str, list[str]] = {}
    for key, meta in manager.API_KEY_REGISTRY.items():
        cat = meta["category"]
        if cat not in cat_keys:
            cat_keys[cat] = []
        cat_keys[cat].append(key)

    # Category icons
    cat_icons = {
        "AI / LLM": "🤖",
        "Google APIs": "🔍",
        "SEO Tools (Optional)": "📈",
        "Email / Outreach": "📧",
        "App Settings": "⚙️",
    }

    # Render each category
    changed_values = {}

    for category in categories:
        keys = cat_keys.get(category, [])
        icon = cat_icons.get(category, "🔧")

        # Count configured in this category
        cat_configured = sum(1 for k in keys if status.get(k, {}).get("configured"))
        cat_total = len(keys)

        # Category expander
        with st.expander(
            f"{icon} **{category}** — {cat_configured}/{cat_total} configured",
            expanded=(cat_configured < cat_total and any(
                manager.API_KEY_REGISTRY[k].get("required") for k in keys
            )),
        ):
            for key in keys:
                meta = manager.API_KEY_REGISTRY[key]
                current_value = env_vars.get(key, "")
                is_configured = bool(current_value)
                is_required = meta.get("required", False)
                is_secret = meta.get("is_secret", False) or "KEY" in key or "PASSWORD" in key or "SECRET" in key
                is_path = meta.get("is_path", False)

                # Key card
                col_status, col_input, col_action = st.columns([0.6, 2, 0.8])

                with col_status:
                    if is_configured:
                        st.markdown(f"""<div style="background:#dcfce7; color:#16a34a;
                            padding:6px 12px; border-radius:8px; text-align:center;
                            font-weight:600; font-size:0.8rem; margin-top:28px;">✅ Active</div>""",
                            unsafe_allow_html=True)
                    elif is_required:
                        st.markdown(f"""<div style="background:#fee2e2; color:#dc2626;
                            padding:6px 12px; border-radius:8px; text-align:center;
                            font-weight:600; font-size:0.8rem; margin-top:28px;">🔴 Required</div>""",
                            unsafe_allow_html=True)
                    else:
                        st.markdown(f"""<div style="background:#f1f5f9; color:#64748b;
                            padding:6px 12px; border-radius:8px; text-align:center;
                            font-weight:600; font-size:0.8rem; margin-top:28px;">⚪ Optional</div>""",
                            unsafe_allow_html=True)

                with col_input:
                    label = f"{meta['icon']} {meta['label']}"
                    help_text = meta["description"]
                    if meta.get("docs_url"):
                        help_text += f" | [📖 Docs]({meta['docs_url']})"

                    if key == "LOG_LEVEL":
                        new_val = st.selectbox(
                            label,
                            ["INFO", "DEBUG", "WARNING", "ERROR"],
                            index=["INFO", "DEBUG", "WARNING", "ERROR"].index(
                                current_value if current_value in ["INFO", "DEBUG", "WARNING", "ERROR"] else "INFO"
                            ),
                            key=f"input_{key}",
                            help=help_text,
                        )
                    elif key == "SMTP_PORT":
                        new_val = st.selectbox(
                            label,
                            ["587", "465", "25", "2525"],
                            index=["587", "465", "25", "2525"].index(
                                current_value if current_value in ["587", "465", "25", "2525"] else "587"
                            ),
                            key=f"input_{key}",
                            help=help_text,
                        )
                    elif is_secret and not is_path:
                        new_val = st.text_input(
                            label,
                            value=current_value,
                            type="password",
                            key=f"input_{key}",
                            help=help_text,
                            placeholder=f"Enter {meta['label']}...",
                        )
                    else:
                        new_val = st.text_input(
                            label,
                            value=current_value,
                            key=f"input_{key}",
                            help=help_text,
                            placeholder=f"Enter {meta['label']}...",
                        )

                    if new_val != current_value:
                        changed_values[key] = new_val

                with col_action:
                    st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
                    # Test button (if test function available)
                    test_val = new_val if key in changed_values else current_value
                    if key in TEST_FUNCTIONS and test_val:
                        if st.button("🧪 Test", key=f"test_{key}", use_container_width=True):
                            with st.spinner("Testing..."):
                                success, msg = TEST_FUNCTIONS[key](test_val)
                            if success:
                                st.success(msg, icon="✅")
                            else:
                                st.error(msg, icon="❌")
                    elif key == "SMTP_HOST":
                        if st.button("🧪 Test", key=f"test_smtp", use_container_width=True):
                            smtp_host = changed_values.get("SMTP_HOST", env_vars.get("SMTP_HOST", ""))
                            smtp_port = changed_values.get("SMTP_PORT", env_vars.get("SMTP_PORT", "587"))
                            smtp_user = changed_values.get("SMTP_USERNAME", env_vars.get("SMTP_USERNAME", ""))
                            smtp_pass = changed_values.get("SMTP_PASSWORD", env_vars.get("SMTP_PASSWORD", ""))
                            if smtp_host and smtp_user and smtp_pass:
                                with st.spinner("Testing SMTP..."):
                                    success, msg = test_smtp_connection(smtp_host, smtp_port, smtp_user, smtp_pass)
                                if success:
                                    st.success(msg, icon="✅")
                                else:
                                    st.error(msg, icon="❌")
                            else:
                                st.warning("Fill all SMTP fields first")
                    elif meta.get("docs_url"):
                        st.link_button("📖 Docs", meta["docs_url"], use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<hr style='margin:8px 0; border:none; border-top:1px solid #f1f5f9'>",
                            unsafe_allow_html=True)

    # Custom API Keys section
    st.markdown("---")
    with st.expander("🔧 **Add Custom API Key** — For new integrations & upgrades", expanded=False):
        st.markdown(
            "Add any additional API key not in the default list. "
            "Useful when upgrading to new tools or adding custom integrations."
        )

        col_name, col_val = st.columns(2)
        with col_name:
            custom_key_name = st.text_input(
                "Key Name",
                placeholder="e.g., MYFAVORITE_API_KEY",
                key="custom_key_name",
                help="Use UPPER_SNAKE_CASE convention",
            )
        with col_val:
            custom_key_value = st.text_input(
                "Key Value",
                type="password",
                placeholder="Enter the API key value...",
                key="custom_key_value",
            )

        if st.button("➕ Add Custom Key", type="primary"):
            if custom_key_name and custom_key_value:
                name = custom_key_name.upper().replace(" ", "_").replace("-", "_")
                changed_values[name] = custom_key_value
                st.success(f"Added `{name}` — click **Save All** to persist.")
            else:
                st.warning("Please provide both key name and value.")

        # Show existing custom keys
        custom_keys = {k: v for k, v in env_vars.items() if k not in manager.API_KEY_REGISTRY}
        if custom_keys:
            st.markdown("**Existing Custom Keys:**")
            for ck, cv in custom_keys.items():
                cc1, cc2, cc3 = st.columns([1, 2, 0.5])
                with cc1:
                    st.code(ck)
                with cc2:
                    st.text_input(
                        "Value", value=cv, type="password",
                        key=f"custom_{ck}", label_visibility="collapsed"
                    )
                with cc3:
                    if st.button("🗑️", key=f"del_{ck}"):
                        manager.delete_key(ck)
                        st.success(f"Deleted `{ck}`")
                        st.rerun()

    # Save / Reset buttons
    st.markdown("---")

    col_save, col_reset, col_export, col_spacer = st.columns([1, 1, 1, 2])

    with col_save:
        if st.button("💾 Save All Settings", type="primary", use_container_width=True):
            # Merge all current form values
            all_values = dict(env_vars)

            # Get all values from form inputs
            for key in manager.API_KEY_REGISTRY:
                form_key = f"input_{key}"
                if form_key in st.session_state:
                    all_values[key] = st.session_state[form_key]

            # Add explicitly changed values
            all_values.update(changed_values)

            # Remove empty values
            all_values = {k: v for k, v in all_values.items() if v}

            manager.save_env(all_values)

            # Update os.environ
            for k, v in all_values.items():
                os.environ[k] = v

            st.success("✅ All settings saved successfully!", icon="💾")
            st.balloons()
            st.rerun()

    with col_reset:
        if st.button("🔄 Reload", use_container_width=True):
            if "settings_values" in st.session_state:
                del st.session_state.settings_values
            st.rerun()

    with col_export:
        if st.button("📋 Export as .env.backup", use_container_width=True):
            backup_path = project_root / f".env.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            env_path = project_root / ".env"
            if env_path.exists():
                import shutil
                shutil.copy(env_path, backup_path)
                st.success(f"Backup saved to `{backup_path.name}`")
            else:
                st.warning("No .env file found to backup.")

    # Info section
    st.markdown("---")
    with st.expander("ℹ️ **Help & Information**", expanded=False):
        st.markdown("""
        ### How API Keys Work

        1. **Required keys** (🔴) must be configured for core functionality
        2. **Optional keys** (⚪) enable additional features and better data
        3. All keys are stored locally in your `.env` file — **never uploaded anywhere**
        4. Use the **🧪 Test** button to verify your key works before saving

        ### Budget Tiers

        | Tier | Monthly Cost | What You Get |
        |:----:|:------------:|------|
        | 🟢 Budget | $20-50 | Free APIs + GPT-4o-mini |
        | 🟡 Standard | $50-250 | + Gemini + more AI usage |
        | 🔴 Premium | $150-500 | + SEMrush/Ahrefs + DataForSEO |

        ### Getting API Keys

        - **OpenAI**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
        - **Gemini**: [aistudio.google.com](https://aistudio.google.com/app/apikey)
        - **Google Cloud**: [console.cloud.google.com](https://console.cloud.google.com/iam-admin/serviceaccounts)
        - **SerpAPI**: [serpapi.com](https://serpapi.com/) (100 free searches/month)

        ### Security

        - `.env` file is in your `.gitignore` — it won't be committed to git
        - Backups are created automatically before each save
        - Keys are masked in the UI for security
        """)


# Allow standalone testing
if __name__ == "__main__":
    render_settings_page()
