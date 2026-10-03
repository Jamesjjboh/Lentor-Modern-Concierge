"""Firestore database layer for Lentor Modern Concierge.
Handles users, query logs, and community tips moderation queue.
Supports graceful fallback to an in-memory/mock store when GCP credentials are not yet configured.
"""

import logging
from datetime import datetime, timezone
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
        doc_ref.set(log_entry)
        return doc_ref.id

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

    # --- Analytics & Content Gaps ---
    def get_analytics_summary(self) -> Dict[str, Any]:
        """Summarizes total users, total queries, and unresolved queries for admin."""
        if self._mock_mode or not self.db:
            total_users = len(self._mock_users)
            total_queries = len(self._mock_logs)
            unanswered = [
                log["user_query"] for log in self._mock_logs
                if not log.get("answered_successfully", True)
            ]
            return {
                "total_users": total_users,
                "total_queries": total_queries,
                "unanswered_count": len(unanswered),
                "unanswered_examples": unanswered[:5],
            }

        users_count = len(list(self.db.collection("users").limit(1000).stream()))
        unanswered_docs = (
            self.db.collection("query_logs")
            .where("answered_successfully", "==", False)
            .limit(10)
            .stream()
        )
        unanswered_queries = [d.to_dict().get("user_query", "") for d in unanswered_docs]

        return {
            "total_users": users_count,
            "unanswered_count": len(unanswered_queries),
            "unanswered_examples": unanswered_queries[:5],
        }


# Global singleton instance
db_client = DatabaseClient()
