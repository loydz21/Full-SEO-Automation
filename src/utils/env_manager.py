"""Environment variable manager for API keys and settings.

Provides secure read/write access to .env file for managing
API keys, credentials, and configuration values.
"""

import os
import re
from pathlib import Path
from typing import Optional
from datetime import datetime


class EnvManager:
    """Manages .env file for API keys and configuration."""

    # Define all supported API keys with metadata
    API_KEY_REGISTRY = {
        # AI / LLM
        "OPENAI_API_KEY": {
            "category": "AI / LLM",
            "label": "OpenAI API Key",
            "description": "GPT-4o-mini for content generation, analysis, and optimization",
            "required": True,
            "prefix": "sk-",
            "docs_url": "https://platform.openai.com/api-keys",
            "icon": "🤖",
        },
        "GOOGLE_GEMINI_API_KEY": {
            "category": "AI / LLM",
            "label": "Google Gemini API Key",
            "description": "Free backup AI (Gemini 2.0 Flash) for bulk tasks",
            "required": False,
            "prefix": "AI",
            "docs_url": "https://aistudio.google.com/app/apikey",
            "icon": "💎",
        },

        # Google APIs
        "GOOGLE_APPLICATION_CREDENTIALS": {
            "category": "Google APIs",
            "label": "Google Service Account JSON Path",
            "description": "Path to service account JSON file for GSC, GA4 access",
            "required": True,
            "prefix": "",
            "docs_url": "https://console.cloud.google.com/iam-admin/serviceaccounts",
            "icon": "🔑",
            "is_path": True,
        },
        "GSC_SITE_URL": {
            "category": "Google APIs",
            "label": "Google Search Console Site URL",
            "description": "Your verified site URL in GSC (e.g., https://yourdomain.com)",
            "required": True,
            "prefix": "http",
            "docs_url": "https://search.google.com/search-console",
            "icon": "🔍",
        },
        "GA4_PROPERTY_ID": {
            "category": "Google APIs",
            "label": "Google Analytics 4 Property ID",
            "description": "Your GA4 property ID (numeric, e.g., 123456789)",
            "required": False,
            "prefix": "",
            "docs_url": "https://analytics.google.com",
            "icon": "📊",
        },
        "PAGESPEED_API_KEY": {
            "category": "Google APIs",
            "label": "PageSpeed Insights API Key",
            "description": "Optional API key for higher rate limits (works without key too)",
            "required": False,
            "prefix": "AI",
            "docs_url": "https://developers.google.com/speed/docs/insights/v5/get-started",
            "icon": "⚡",
        },

        # SEO Tools (Optional Upgrades)
        "SEMRUSH_API_KEY": {
            "category": "SEO Tools (Optional)",
            "label": "SEMrush API Key",
            "description": "For keyword data, backlinks, competitor analysis ($100+/mo)",
            "required": False,
            "prefix": "",
            "docs_url": "https://www.semrush.com/api/",
            "icon": "📈",
        },
        "AHREFS_API_KEY": {
            "category": "SEO Tools (Optional)",
            "label": "Ahrefs API Key",
            "description": "For backlink analysis, keyword data ($99+/mo)",
            "required": False,
            "prefix": "",
            "docs_url": "https://ahrefs.com/api",
            "icon": "🔗",
        },
        "DATAFORSEO_LOGIN": {
            "category": "SEO Tools (Optional)",
            "label": "DataForSEO Login",
            "description": "Login email for DataForSEO keyword/SERP API ($50+/mo)",
            "required": False,
            "prefix": "",
            "docs_url": "https://dataforseo.com/",
            "icon": "📦",
        },
        "DATAFORSEO_PASSWORD": {
            "category": "SEO Tools (Optional)",
            "label": "DataForSEO Password",
            "description": "Password for DataForSEO API",
            "required": False,
            "prefix": "",
            "docs_url": "https://dataforseo.com/",
            "icon": "📦",
            "is_secret": True,
        },
        "SERPAPI_KEY": {
            "category": "SEO Tools (Optional)",
            "label": "SerpAPI Key",
            "description": "SERP scraping API — free tier: 100 searches/mo",
            "required": False,
            "prefix": "",
            "docs_url": "https://serpapi.com/",
            "icon": "🌐",
        },

        # Email / Outreach
        "SMTP_HOST": {
            "category": "Email / Outreach",
            "label": "SMTP Host",
            "description": "Email server host (e.g., smtp.gmail.com)",
            "required": False,
            "prefix": "",
            "docs_url": "",
            "icon": "📧",
        },
        "SMTP_PORT": {
            "category": "Email / Outreach",
            "label": "SMTP Port",
            "description": "Email server port (e.g., 587 for TLS)",
            "required": False,
            "prefix": "",
            "docs_url": "",
            "icon": "📧",
        },
        "SMTP_USERNAME": {
            "category": "Email / Outreach",
            "label": "SMTP Username",
            "description": "Email login username",
            "required": False,
            "prefix": "",
            "docs_url": "",
            "icon": "📧",
        },
        "SMTP_PASSWORD": {
            "category": "Email / Outreach",
            "label": "SMTP Password",
            "description": "Email login password or app password",
            "required": False,
            "prefix": "",
            "docs_url": "",
            "icon": "📧",
            "is_secret": True,
        },

        # Application Settings
        "MONTHLY_BUDGET_LIMIT": {
            "category": "App Settings",
            "label": "Monthly API Budget Limit ($)",
            "description": "Maximum monthly spend on APIs (default: 100)",
            "required": False,
            "prefix": "",
            "docs_url": "",
            "icon": "💰",
        },
        "DEFAULT_DOMAIN": {
            "category": "App Settings",
            "label": "Default Target Domain",
            "description": "Your primary website domain for SEO tracking",
            "required": True,
            "prefix": "",
            "docs_url": "",
            "icon": "🌐",
        },
        "LOG_LEVEL": {
            "category": "App Settings",
            "label": "Log Level",
            "description": "Logging verbosity: DEBUG, INFO, WARNING, ERROR",
            "required": False,
            "prefix": "",
            "docs_url": "",
            "icon": "📋",
        },
    }

    def __init__(self, env_path: Optional[str] = None):
        """Initialize with path to .env file."""
        if env_path:
            self.env_path = Path(env_path)
        else:
            self.env_path = Path(__file__).parent.parent.parent / ".env"

    def load_env(self) -> dict[str, str]:
        """Load all variables from .env file."""
        env_vars = {}
        if not self.env_path.exists():
            return env_vars

        with open(self.env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'") 
                    env_vars[key] = value
        return env_vars

    def save_env(self, env_vars: dict[str, str]) -> None:
        """Save variables to .env file, preserving comments and structure."""
        # Backup existing file
        if self.env_path.exists():
            backup_path = self.env_path.with_suffix(".env.backup")
            with open(self.env_path, "r") as f:
                backup_content = f.read()
            with open(backup_path, "w") as f:
                f.write(backup_content)

        # Group keys by category
        categories: dict[str, list[str]] = {}
        for key, meta in self.API_KEY_REGISTRY.items():
            cat = meta["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(key)

        # Write organized .env file
        lines = []
        lines.append(f"# Full SEO Automation — Environment Configuration")
        lines.append(f"# Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}") 
        lines.append(f"# WARNING: Keep this file private. Never commit to version control.")
        lines.append("")

        for category, keys in categories.items():
            lines.append(f"# {'=' * 50}")
            lines.append(f"# {category}")
            lines.append(f"# {'=' * 50}")
            for key in keys:
                meta = self.API_KEY_REGISTRY[key]
                value = env_vars.get(key, "")
                lines.append(f"# {meta['description']}")
                if value:
                    lines.append(f'{key}="{value}"') 
                else:
                    lines.append(f"{key}=")
                lines.append("")
            lines.append("")

        # Add any custom keys not in registry
        custom_keys = [k for k in env_vars if k not in self.API_KEY_REGISTRY]
        if custom_keys:
            lines.append(f"# {'=' * 50}")
            lines.append(f"# Custom / Additional Keys")
            lines.append(f"# {'=' * 50}")
            for key in custom_keys:
                value = env_vars[key]
                lines.append(f'{key}="{value}"') 
                lines.append("")

        with open(self.env_path, "w") as f:
            f.write("\n".join(lines))

    def get_key(self, key_name: str) -> Optional[str]:
        """Get a single API key value."""
        env_vars = self.load_env()
        value = env_vars.get(key_name, "")
        # Also check os.environ as fallback
        if not value:
            value = os.environ.get(key_name, "")
        return value if value else None

    def set_key(self, key_name: str, value: str) -> None:
        """Set a single API key value."""
        env_vars = self.load_env()
        env_vars[key_name] = value
        self.save_env(env_vars)
        # Also update current process env
        os.environ[key_name] = value

    def delete_key(self, key_name: str) -> None:
        """Remove an API key."""
        env_vars = self.load_env()
        env_vars.pop(key_name, None)
        self.save_env(env_vars)
        os.environ.pop(key_name, None)

    def get_status(self) -> dict[str, dict]:
        """Get configuration status for all registered keys."""
        env_vars = self.load_env()
        status = {}
        for key, meta in self.API_KEY_REGISTRY.items():
            value = env_vars.get(key, "") or os.environ.get(key, "")
            status[key] = {
                **meta,
                "configured": bool(value),
                "value": value,
                "masked_value": self._mask_value(value) if value else "",
            }
        # Add custom keys
        for key, value in env_vars.items():
            if key not in self.API_KEY_REGISTRY:
                status[key] = {
                    "category": "Custom / Additional",
                    "label": key,
                    "description": "Custom API key",
                    "required": False,
                    "prefix": "",
                    "docs_url": "",
                    "icon": "🔧",
                    "configured": bool(value),
                    "value": value,
                    "masked_value": self._mask_value(value) if value else "",
                }
        return status

    def get_categories(self) -> list[str]:
        """Get all unique categories."""
        cats = []
        seen = set()
        for meta in self.API_KEY_REGISTRY.values():
            cat = meta["category"]
            if cat not in seen:
                cats.append(cat)
                seen.add(cat)
        return cats

    def _mask_value(self, value: str) -> str:
        """Mask a value for display (show first 4 and last 4 chars)."""
        if not value:
            return ""
        if len(value) <= 10:
            return "*" * len(value)
        return value[:4] + "*" * (len(value) - 8) + value[-4:]

    def ensure_env_exists(self) -> None:
        """Create .env file from .env.example if it doesn't exist."""
        if not self.env_path.exists():
            example_path = self.env_path.parent / ".env.example"
            if example_path.exists():
                import shutil
                shutil.copy(example_path, self.env_path)
            else:
                self.save_env({})


# Singleton instance
_manager: Optional[EnvManager] = None

def get_env_manager(env_path: Optional[str] = None) -> EnvManager:
    """Get or create singleton EnvManager instance."""
    global _manager
    if _manager is None:
        _manager = EnvManager(env_path)
    return _manager
