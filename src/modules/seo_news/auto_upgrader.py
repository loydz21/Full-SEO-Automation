"""SEO Auto Upgrader — Applies verified strategies to the automation system.

Takes verified SEO strategies and applies them by updating configurations,
adding new checks to audit modules, updating content templates, and
logging all changes for review.
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Module mapping for strategy application
MODULE_PATHS = {
    "technical_seo": "src/modules/technical_audit",
    "onpage_seo": "src/modules/onpage_seo",
    "offpage_seo": "src/modules/link_building",
    "local_seo": "src/modules/local_seo",
    "content_strategy": "src/modules/blog_content",
    "link_building": "src/modules/link_building",
    "core_web_vitals": "src/modules/technical_audit",
    "schema_markup": "src/modules/onpage_seo",
    "keyword_research": "src/modules/keyword_research",
    "content_optimizer": "src/modules/content_optimizer",
}


class SEOAutoUpgrader:
    """Applies verified SEO strategies to the automation system."""

    def __init__(self, project_root: str = "/a0/usr/projects/fullseoautomation"):
        """Initialize the auto upgrader.

        Args:
            project_root: Root directory of the SEO automation project.
        """
        self.project_root = Path(project_root)
        self.config_path = self.project_root / "config" / "settings.yaml"
        self.upgrade_log_dir = self.project_root / "data" / "upgrade_logs"
        self.upgrade_log_dir.mkdir(parents=True, exist_ok=True)
        self._upgrade_history: list[dict] = []
        self._load_history()

    def _load_history(self):
        """Load upgrade history from disk."""
        history_file = self.upgrade_log_dir / "history.json"
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    self._upgrade_history = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._upgrade_history = []

    def _save_history(self):
        """Save upgrade history to disk."""
        history_file = self.upgrade_log_dir / "history.json"
        with open(history_file, "w") as f:
            json.dump(self._upgrade_history, f, indent=2, default=str)

    def apply_strategy(self, strategy: dict, upgrade_plan: dict) -> dict:
        """Apply a verified strategy to the system.

        Args:
            strategy: Verified strategy dict from analyzer.
            upgrade_plan: Upgrade plan dict from analyzer.

        Returns:
            Result dict with status, changes_made, and any errors.
        """
        result = {
            "strategy_title": strategy.get("title", ""),
            "applied_at": datetime.utcnow().isoformat(),
            "changes_made": [],
            "errors": [],
            "status": "pending",
        }

        logger.info("Applying strategy: %s", strategy.get("title", ""))

        # Check if auto-applicable
        if upgrade_plan.get("auto_applicable", False):
            # Apply config changes directly
            config_changes = upgrade_plan.get("config_changes", {})
            if config_changes:
                change = self._apply_config_changes(config_changes)
                result["changes_made"].append(change)

        # Process each required change
        for change_req in upgrade_plan.get("changes_required", []):
            change_type = change_req.get("change_type", "")

            try:
                if change_type == "config_update":
                    change = self._apply_config_changes(
                        {change_req["module"]: change_req.get("implementation_detail", "")}
                    )
                elif change_type == "new_check":
                    change = self._add_audit_check(change_req)
                elif change_type == "new_feature":
                    change = self._create_feature_stub(change_req)
                elif change_type == "enhancement":
                    change = self._log_enhancement(change_req)
                else:
                    change = {
                        "type": "manual",
                        "description": f"Manual change needed: {change_req.get("description", "")}",
                        "status": "pending_manual",
                    }

                result["changes_made"].append(change)

            except Exception as e:
                error_msg = f"Failed to apply change {change_type}: {e}"
                logger.error(error_msg)
                result["errors"].append(error_msg)

        # Update status
        if result["errors"]:
            result["status"] = "partial" if result["changes_made"] else "failed"
        else:
            result["status"] = "applied"

        # Save to history
        self._upgrade_history.append(result)
        self._save_history()

        # Save detailed log
        self._save_upgrade_log(strategy, upgrade_plan, result)

        logger.info(
            "Strategy applied: %s (status: %s, changes: %d, errors: %d)",
            strategy.get("title", ""),
            result["status"],
            len(result["changes_made"]),
            len(result["errors"]),
        )

        return result

    def _apply_config_changes(self, changes: dict) -> dict:
        """Apply changes to the settings.yaml config file."""
        import yaml

        # Backup current config
        if self.config_path.exists():
            backup_name = f"settings.yaml.bak.{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            backup_path = self.config_path.parent / backup_name
            shutil.copy2(self.config_path, backup_path)

        # Load current config
        config = {}
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f) or {}

        # Apply changes
        seo_strategies = config.setdefault("applied_strategies", [])
        seo_strategies.append({
            "changes": changes,
            "applied_at": datetime.utcnow().isoformat(),
        })

        # Save updated config
        with open(self.config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        return {
            "type": "config_update",
            "description": f"Updated settings.yaml with {len(changes)} changes",
            "status": "applied",
            "details": changes,
        }

    def _add_audit_check(self, change_req: dict) -> dict:
        """Add a new check to the audit checklist files."""
        module = change_req.get("module", "")
        module_path = MODULE_PATHS.get(module, "")

        if not module_path:
            module_path = f"src/modules/{module}"

        # Create a checks registry file if it does not exist
        checks_dir = self.project_root / module_path
        checks_file = checks_dir / "custom_checks.json"

        # Load existing checks
        existing_checks = []
        if checks_file.exists():
            try:
                with open(checks_file, "r") as f:
                    existing_checks = json.load(f)
            except (json.JSONDecodeError, IOError):
                existing_checks = []

        # Add new check
        new_check = {
            "id": f"custom_{len(existing_checks) + 1}",
            "name": change_req.get("description", "New Check"),
            "detail": change_req.get("implementation_detail", ""),
            "priority": change_req.get("priority", "medium"),
            "added_at": datetime.utcnow().isoformat(),
            "source": "seo_news_auto_upgrade",
        }
        existing_checks.append(new_check)

        # Save
        checks_dir.mkdir(parents=True, exist_ok=True)
        with open(checks_file, "w") as f:
            json.dump(existing_checks, f, indent=2)

        return {
            "type": "new_check",
            "description": f"Added check to {module}: {new_check['name']}",
            "status": "applied",
            "file": str(checks_file),
        }

    def _create_feature_stub(self, change_req: dict) -> dict:
        """Create a stub file for a new feature to be implemented."""
        module = change_req.get("module", "unknown")
        module_path = MODULE_PATHS.get(module, f"src/modules/{module}")
        feature_dir = self.project_root / module_path / "pending_features"
        feature_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        feature_file = feature_dir / f"feature_{timestamp}.md"

        content = f"""# Pending Feature: {change_req.get("description", "New Feature")}

## Module: {module}
## Priority: {change_req.get("priority", "medium")}
## Created: {datetime.utcnow().isoformat()}
## Source: SEO News Auto-Upgrade

## Description
{change_req.get("description", "No description")}

## Implementation Details
{change_req.get("implementation_detail", "No details provided")}

## Status: Pending Implementation
"""

        with open(feature_file, "w") as f:
            f.write(content)

        return {
            "type": "new_feature",
            "description": f"Feature stub created: {change_req.get('description', '')}",
            "status": "stub_created",
            "file": str(feature_file),
        }

    def _log_enhancement(self, change_req: dict) -> dict:
        """Log an enhancement request for manual implementation."""
        enhancements_file = self.upgrade_log_dir / "pending_enhancements.json"

        existing = []
        if enhancements_file.exists():
            try:
                with open(enhancements_file, "r") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, IOError):
                existing = []

        enhancement = {
            "id": f"enh_{len(existing) + 1}",
            "module": change_req.get("module", ""),
            "description": change_req.get("description", ""),
            "detail": change_req.get("implementation_detail", ""),
            "priority": change_req.get("priority", "medium"),
            "logged_at": datetime.utcnow().isoformat(),
            "status": "pending",
        }
        existing.append(enhancement)

        with open(enhancements_file, "w") as f:
            json.dump(existing, f, indent=2)

        return {
            "type": "enhancement",
            "description": f"Enhancement logged: {change_req.get('description', '')}",
            "status": "logged",
            "file": str(enhancements_file),
        }

    def _save_upgrade_log(self, strategy: dict, plan: dict, result: dict):
        """Save a detailed log of the upgrade."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_file = self.upgrade_log_dir / f"upgrade_{timestamp}.json"

        log_entry = {
            "strategy": {
                "title": strategy.get("title", ""),
                "description": strategy.get("description", ""),
                "category": strategy.get("category", ""),
                "confidence": strategy.get("confidence_score", 0),
                "source": strategy.get("source_article", {}),
            },
            "upgrade_plan": plan,
            "result": result,
        }

        with open(log_file, "w") as f:
            json.dump(log_entry, f, indent=2, default=str)

    def get_upgrade_history(self) -> list[dict]:
        """Get all upgrade history entries."""
        return self._upgrade_history

    def get_pending_enhancements(self) -> list[dict]:
        """Get all pending enhancements."""
        enhancements_file = self.upgrade_log_dir / "pending_enhancements.json"
        if enhancements_file.exists():
            try:
                with open(enhancements_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def get_pending_features(self) -> list[dict]:
        """Scan all modules for pending feature stubs."""
        features = []
        for module_name, module_path in MODULE_PATHS.items():
            feature_dir = self.project_root / module_path / "pending_features"
            if feature_dir.exists():
                for f in feature_dir.glob("*.md"):
                    features.append({
                        "module": module_name,
                        "file": str(f),
                        "name": f.stem,
                        "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    })
        return features

    def rollback_last_upgrade(self) -> dict:
        """Rollback the last applied upgrade by restoring config backup."""
        backup_dir = self.config_path.parent
        backups = sorted(backup_dir.glob("settings.yaml.bak.*"))

        if not backups:
            return {"status": "error", "message": "No backups found"}

        latest_backup = backups[-1]
        shutil.copy2(latest_backup, self.config_path)

        # Mark last history entry as rolled back
        if self._upgrade_history:
            self._upgrade_history[-1]["status"] = "rolled_back"
            self._save_history()

        return {
            "status": "rolled_back",
            "restored_from": str(latest_backup),
            "message": "Config restored from latest backup",
        }
