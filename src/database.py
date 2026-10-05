"""Firestore database layer for Lentor Modern Concierge.
Handles users, query logs, and community tips moderation queue.
Supports graceful fallback to an in-memory/mock store when GCP credentials are not yet configured.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore
from src.config import GCP_PROJECT_ID, FIRESTORE_DATABASE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseClient:
    def __init__(self, project_id: Optional[str] = None, database: str = "(default)"):
        self.project_id = project_id or GCP_PROJECT_ID
        self.database_name = database or FIRESTORE_DATABASE
        self.db: Optional[firestore.Client] = None
        self._mock_mode = False
        
        # In-memory mock storage for development if Firestore is unavailable
        self._mock_users: Dict[str, Dict[str, Any]] = {}
        self._mock_logs: List[Dict[str, Any]] = []
        self._mock_tips: Dict[str, Dict[str, Any]] = {}
        self._mock_tip_counter = 1
        self._mock_feedback: Dict[str, Dict[str, Any]] = {}
        self._mock_feedback_counter = 1
        self._mock_reply_mappings: Dict[str, Dict[str, Any]] = {}

        self._init_client()

    def _init_client(self):
        try:
            if self.project_id:
                self.db = firestore.Client(project=self.project_id, database=self.database_name)
                logger.info(f"Connected to Cloud Firestore (Project: {self.project_id}, Database: {self.database_name})")
            else:
                logger.warning("GCP_PROJECT_ID not set. Running DatabaseClient in local in-memory fallback mode.")
                self._mock_mode = True
        except Exception as e:
            logger.warning(f"Could not connect to Firestore ({e}). Falling back to local in-memory store.")
            self._mock_mode = True

    # --- User Management ---
    def get_or_create_user(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> Dict[str, Any]:
        user_key = str(user_id)
        now = datetime.now(timezone.utc).isoformat()

        if self._mock_mode or not self.db:
            if user_key not in self._mock_users:
                self._mock_users[user_key] = {
                    "user_id": user_key,
                    "username": username,
                    "first_name": first_name,
                    "first_seen": now,
                    "last_active": now,
                    "total_queries": 0,
                    "opted_in_broadcasts": True,
                }
            else:
                self._mock_users[user_key]["last_active"] = now
                if username:
                    self._mock_users[user_key]["username"] = username
                if first_name:
                    self._mock_users[user_key]["first_name"] = first_name
            return self._mock_users[user_key]

        user_ref = self.db.collection("users").document(user_key)
        doc = user_ref.get()

        if not doc.exists:
            user_data = {
                "user_id": user_key,
                "username": username,
                "first_name": first_name,
                "first_seen": now,
                "last_active": now,
                "total_queries": 0,
                "opted_in_broadcasts": True,
            }
            user_ref.set(user_data)
            return user_data
        else:
            updates = {"last_active": now}
            if username:
                updates["username"] = username
            if first_name:
                updates["first_name"] = first_name
            user_ref.update(updates)
            data = doc.to_dict() or {}
            data.update(updates)
            return data

    def increment_user_query(self, user_id: int):
        user_key = str(user_id)
        if self._mock_mode or not self.db:
            if user_key in self._mock_users:
                self._mock_users[user_key]["total_queries"] = self._mock_users[user_key].get("total_queries", 0) + 1
            return

        user_ref = self.db.collection("users").document(user_key)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(user_ref.update, {"total_queries": firestore.Increment(1)}))
        except RuntimeError:
            user_ref.update({"total_queries": firestore.Increment(1)})

    # --- Query Logging (Content Gap Detection) ---
    def log_query(
        self,
        user_id: int,
        user_query: str,
        tools_called: List[str],
        agent_response: str,
        answered_successfully: bool = True,
        feedback: Optional[str] = None,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()
        log_entry = {
            "user_id": str(user_id),
            "timestamp": now,
            "user_query": user_query,
            "tools_called": tools_called,
            "agent_response": agent_response,
            "answered_successfully": answered_successfully,
            "feedback": feedback,
        }

        if self._mock_mode or not self.db:
            log_id = f"log_{len(self._mock_logs) + 1}"
            log_entry["log_id"] = log_id
            self._mock_logs.append(log_entry)
            return log_id

        doc_ref = self.db.collection("query_logs").document()
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(doc_ref.set, log_entry))
        except RuntimeError:
            doc_ref.set(log_entry)
        return doc_ref.id

    def update_query_feedback(
        self,
        log_id: str,
        feedback: str,
    ) -> bool:
        """Updates resident feedback (e.g. 'helpful' or 'inaccurate') on a logged query."""
        now = datetime.now(timezone.utc).isoformat()
        if self._mock_mode or not self.db:
            for entry in self._mock_logs:
                if entry.get("log_id") == log_id:
                    entry["feedback"] = feedback
                    entry["feedback_at"] = now
                    return True
            return False

        doc_ref = self.db.collection("query_logs").document(log_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        doc_ref.update({"feedback": feedback, "feedback_at": now})
        return True

    def get_query_log(self, log_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a logged query by log_id."""
        if self._mock_mode or not self.db:
            for entry in self._mock_logs:
                if entry.get("log_id") == log_id:
                    return entry
            return None

        doc = self.db.collection("query_logs").document(log_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["log_id"] = doc.id
            return data
        return None

    def get_flagged_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves recent queries marked as inaccurate or flagged by residents."""
        if self._mock_mode or not self.db:
            flagged = [
                entry for entry in reversed(self._mock_logs)
                if entry.get("feedback") == "inaccurate"
            ]
            return flagged[:limit]

        query = (
            self.db.collection("query_logs")
            .where("feedback", "==", "inaccurate")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        results = []
        try:
            for d in query.stream():
                item = d.to_dict()
                item["log_id"] = d.id
                results.append(item)
        except Exception as e:
            logger.warning(f"Failed query with ordering: {e}, falling back to unordered query")
            fallback = self.db.collection("query_logs").where("feedback", "==", "inaccurate").limit(limit)
            for d in fallback.stream():
                item = d.to_dict()
                item["log_id"] = d.id
                results.append(item)
        return results

    def submit_community_tip(
        self,
        user_id: int,
        topic: str,
        content: str,
        has_image: bool = False,
        image_summary: Optional[str] = None,
    ) -> str:
        """Submits a new tip into the moderation queue with status 'pending'."""
        now = datetime.now(timezone.utc).isoformat()
        tip_data = {
            "topic": topic.strip().lower(),
            "content": content.strip(),
            "status": "pending",
            "submitted_by_user_id": str(user_id),
            "submitted_at": now,
            "reviewed_at": None,
            "has_image": has_image,
            "image_summary": image_summary,
        }

        if self._mock_mode or not self.db:
            tip_id = f"tip_{self._mock_tip_counter}"
            self._mock_tip_counter += 1
            tip_data["tip_id"] = tip_id
            self._mock_tips[tip_id] = tip_data
            return tip_id

        doc_ref = self.db.collection("community_tips").document()
        doc_ref.set(tip_data)
        return doc_ref.id


    def update_tip_status(self, tip_id: str, status: str) -> bool:
        """Admin action: approve or reject a community tip."""
        if status not in ("approved", "rejected", "pending"):
            raise ValueError(f"Invalid status: {status}")

        now = datetime.now(timezone.utc).isoformat()
        if self._mock_mode or not self.db:
            if tip_id in self._mock_tips:
                self._mock_tips[tip_id]["status"] = status
                self._mock_tips[tip_id]["reviewed_at"] = now
                return True
            return False

        tip_ref = self.db.collection("community_tips").document(tip_id)
        doc = tip_ref.get()
        if not doc.exists:
            return False
        tip_ref.update({"status": status, "reviewed_at": now})
        return True

    def get_tip_by_id(self, tip_id: str) -> Optional[Dict[str, Any]]:
        if self._mock_mode or not self.db:
            return self._mock_tips.get(tip_id)

        doc = self.db.collection("community_tips").document(tip_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["tip_id"] = doc.id
            return data
        return None

    def get_approved_tips(self, topic: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns approved community tips, optionally filtered by topic."""
        if self._mock_mode or not self.db:
            approved = [
                tip for tip in self._mock_tips.values()
                if tip.get("status") == "approved"
            ]
            if topic:
                t_lower = topic.strip().lower()
                approved = [tip for tip in approved if t_lower in tip.get("topic", "")]
            return approved[:limit]

        query = self.db.collection("community_tips").where("status", "==", "approved")
        if topic:
            query = query.where("topic", "==", topic.strip().lower())
        docs = query.limit(limit).stream()
        results = []
        for d in docs:
            item = d.to_dict()
            item["tip_id"] = d.id
            results.append(item)
        return results

    # --- Broadcast Engine Queries ---
    def get_broadcast_subscribers(self, limit: int = 1000) -> List[int]:
        """Fetches all Telegram user IDs who are opted into broadcasts."""
        if self._mock_mode or not self.db:
            return [
                int(u["user_id"])
                for u in self._mock_users.values()
                if u.get("opted_in_broadcasts", True)
            ]

        docs = (
            self.db.collection("users")
            .where("opted_in_broadcasts", "==", True)
            .limit(limit)
            .stream()
        )
        return [int(d.id) for d in docs]

    # --- Resident Feedback & Developer 2-Way Reply ---
    def submit_feedback(
        self,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        category: str,
        message: str,
        has_image: bool = False,
        image_summary: Optional[str] = None,
    ) -> str:
        """Stores resident feedback or bug report with status 'new'."""
        now = datetime.now(timezone.utc).isoformat()
        feedback_data = {
            "user_id": str(user_id),
            "username": username,
            "first_name": first_name,
            "category": category,
            "message": message,
            "has_image": has_image,
            "image_summary": image_summary,
            "created_at": now,
            "status": "new",
            "admin_reply": None,
            "replied_at": None,
        }

        if self._mock_mode or not self.db:
            fb_id = f"fb_{self._mock_feedback_counter}"
            self._mock_feedback_counter += 1
            feedback_data["feedback_id"] = fb_id
            self._mock_feedback[fb_id] = feedback_data
            return fb_id

        doc_ref = self.db.collection("resident_feedback").document()
        feedback_data["feedback_id"] = doc_ref.id
        doc_ref.set(feedback_data)
        return doc_ref.id

    def save_admin_reply_mapping(
        self,
        admin_message_id: int,
        user_id: int,
        resident_name: str,
        feedback_id: str,
    ):
        """Saves a mapping from the Telegram message ID sent to admin to the resident's user ID."""
        mapping_data = {
            "admin_message_id": admin_message_id,
            "user_id": str(user_id),
            "resident_name": resident_name,
            "feedback_id": feedback_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        msg_key = str(admin_message_id)
        if self._mock_mode or not self.db:
            self._mock_reply_mappings[msg_key] = mapping_data
            return

        self.db.collection("admin_reply_mappings").document(msg_key).set(mapping_data)

    def get_admin_reply_mapping(self, admin_message_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves resident mapping info for a replied-to admin message ID."""
        msg_key = str(admin_message_id)
        if self._mock_mode or not self.db:
            return self._mock_reply_mappings.get(msg_key)

        doc = self.db.collection("admin_reply_mappings").document(msg_key).get()
        if doc.exists:
            return doc.to_dict()
        return None

    def update_feedback_status(
        self,
        feedback_id: str,
        status: str,
        admin_reply: Optional[str] = None,
    ) -> bool:
        """Updates status of a feedback entry ('replied' or 'resolved')."""
        now = datetime.now(timezone.utc).isoformat()
        update_data = {
            "status": status,
            "updated_at": now,
        }
        if admin_reply:
            update_data["admin_reply"] = admin_reply
            update_data["replied_at"] = now

        if self._mock_mode or not self.db:
            if feedback_id in self._mock_feedback:
                self._mock_feedback[feedback_id].update(update_data)
                return True
            return False

        doc_ref = self.db.collection("resident_feedback").document(feedback_id)
        doc = doc_ref.get()
        if not doc.exists:
            return False
        doc_ref.update(update_data)
        return True

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Returns counts of total feedback and unresolved items."""
        if self._mock_mode or not self.db:
            total = len(self._mock_feedback)
            unresolved = len([fb for fb in self._mock_feedback.values() if fb.get("status") == "new"])
            return {"total_feedback": total, "unresolved_feedback": unresolved}

        try:
            docs = list(self.db.collection("resident_feedback").limit(500).stream())
            total = len(docs)
            unresolved = len([d for d in docs if d.to_dict().get("status") == "new"])
            return {"total_feedback": total, "unresolved_feedback": unresolved}
        except Exception:
            return {"total_feedback": 0, "unresolved_feedback": 0}

    # --- Analytics & Content Gaps ---
    def _fetch_analytics_inputs(self, days: Optional[int]) -> Dict[str, List[Dict[str, Any]]]:
        """Fetches raw users, query logs (>= max(window, 7 days)), and feedback for analytics."""
        since_days = None if not days else max(days, 7)
        since_iso = (
            (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat() if since_days else None
        )

        if self._mock_mode or not self.db:
            logs = [
                l for l in self._mock_logs
                if since_iso is None or l.get("timestamp", "") >= since_iso
            ]
            return {
                "users": list(self._mock_users.values()),
                "logs": logs,
                "feedback": list(self._mock_feedback.values()),
            }

        users = [d.to_dict() or {} for d in self.db.collection("users").limit(2000).stream()]
        logs_ref = self.db.collection("query_logs")
        if since_iso:
            # Single-field range filter: no composite index required (timestamps are ISO-8601 UTC strings).
            logs_ref = logs_ref.where("timestamp", ">=", since_iso)
        logs = [d.to_dict() or {} for d in logs_ref.limit(5000).stream()]
        feedback = [d.to_dict() or {} for d in self.db.collection("resident_feedback").limit(1000).stream()]
        return {"users": users, "logs": logs, "feedback": feedback}

    def get_analytics_summary(self, days: Optional[int] = 7) -> Dict[str, Any]:
        """Summarizes users, queries, topics, ranked content gaps, and feedback for the last `days` days (None = all time)."""
        from src.analytics import compute_analytics

        try:
            data = self._fetch_analytics_inputs(days)
            return compute_analytics(data["users"], data["logs"], data["feedback"], days=days)
        except Exception as e:
            logger.error(f"Analytics fetch failed: {e}")
            return compute_analytics([], [], [], days=days)


# Global singleton instance
db_client = DatabaseClient()
