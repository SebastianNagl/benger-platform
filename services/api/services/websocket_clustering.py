"""
WebSocket Clustering Module for Horizontal Scaling

Implements Redis-based message broadcasting to enable WebSocket connections
across multiple server instances to communicate with each other.

Features:
- Cross-instance message broadcasting via Redis pub/sub
- Shared connection state management
- Automatic cleanup of stale connections
- Scalable architecture for production deployment
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from redis_cache import get_redis_client

logger = logging.getLogger(__name__)


class WebSocketClusterManager:
    """
    Manages WebSocket clustering using Redis pub/sub for cross-instance communication.

    This allows multiple API server instances to coordinate WebSocket connections
    and broadcast messages across the entire cluster.
    """

    def __init__(self):
        self.redis_client = None
        self.pubsub = None
        self.instance_id = str(uuid.uuid4())
        self.is_listening = False

        # Local connections for this instance
        self.local_connections: Dict[str, Dict[str, Any]] = {}

        # Channel names for Redis pub/sub
        self.MESSAGE_CHANNEL = "websocket:messages"
        self.CONNECTION_CHANNEL = "websocket:connections"
        self.HEARTBEAT_CHANNEL = "websocket:heartbeat"

    async def initialize(self):
        """Initialize Redis connection and start listening for cluster messages"""
        try:
            # Get Redis client (async version)
            redis_client = get_redis_client()

            # Extract connection info from the sync Redis client (including password)
            redis_url = "localhost"
            redis_port = 6379
            redis_db = 0
            redis_password = None
            try:
                pool = getattr(redis_client, "connection_pool", None) or getattr(redis_client, "_connection_pool", None)
                if pool:
                    kwargs = pool.connection_kwargs
                    redis_url = kwargs.get("host", "localhost")
                    redis_port = kwargs.get("port", 6379)
                    redis_db = kwargs.get("db", 0)
                    redis_password = kwargs.get("password")
            except (AttributeError, KeyError):
                pass

            self.redis_client = redis.Redis(
                host=redis_url, port=redis_port, db=redis_db,
                password=redis_password, decode_responses=True,
            )

            # Test connection
            await self.redis_client.ping()

            # Start pub/sub listener
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe(
                self.MESSAGE_CHANNEL, self.CONNECTION_CHANNEL, self.HEARTBEAT_CHANNEL
            )

            # Start background listener task
            asyncio.create_task(self._listen_for_cluster_messages())

            # Start heartbeat task
            asyncio.create_task(self._send_heartbeat())

            self.is_listening = True
            logger.info(f"WebSocket clustering initialized for instance {self.instance_id}")

        except Exception as e:
            logger.error(f"Failed to initialize WebSocket clustering: {e}")
            self.redis_client = None

    async def register_connection(self, project_id: str, user_id: str, websocket_id: str):
        """Register a WebSocket connection with the cluster"""

        # Store locally
        if project_id not in self.local_connections:
            self.local_connections[project_id] = {}

        self.local_connections[project_id][user_id] = {
            "websocket_id": websocket_id,
            "instance_id": self.instance_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }

        # Notify cluster
        if self.redis_client:
            connection_data = {
                "action": "connect",
                "project_id": project_id,
                "user_id": user_id,
                "instance_id": self.instance_id,
                "websocket_id": websocket_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await self.redis_client.publish(self.CONNECTION_CHANNEL, json.dumps(connection_data))

            # Store in shared state with TTL (1 hour)
            key = f"websocket:connection:{project_id}:{user_id}"
            await self.redis_client.setex(key, 3600, json.dumps(connection_data))  # 1 hour TTL

    async def unregister_connection(self, project_id: str, user_id: str):
        """Unregister a WebSocket connection from the cluster"""

        # Remove locally
        if project_id in self.local_connections and user_id in self.local_connections[project_id]:
            del self.local_connections[project_id][user_id]

            if not self.local_connections[project_id]:
                del self.local_connections[project_id]

        # Notify cluster
        if self.redis_client:
            disconnection_data = {
                "action": "disconnect",
                "project_id": project_id,
                "user_id": user_id,
                "instance_id": self.instance_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            await self.redis_client.publish(self.CONNECTION_CHANNEL, json.dumps(disconnection_data))

            # Remove from shared state
            key = f"websocket:connection:{project_id}:{user_id}"
            await self.redis_client.delete(key)

    async def broadcast_to_project(
        self,
        project_id: str,
        message: Dict[str, Any],
        exclude_user: Optional[str] = None,
        exclude_instance: Optional[str] = None,
    ):
        """Broadcast a message to all users in a project across all instances"""

        if not self.redis_client:
            return

        cluster_message = {
            "type": "project_broadcast",
            "project_id": project_id,
            "message": message,
            "exclude_user": exclude_user,
            "exclude_instance": exclude_instance or self.instance_id,
            "source_instance": self.instance_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.redis_client.publish(self.MESSAGE_CHANNEL, json.dumps(cluster_message))

    async def send_to_user(self, project_id: str, user_id: str, message: Dict[str, Any]):
        """Send a message to a specific user across the cluster"""

        if not self.redis_client:
            return False

        cluster_message = {
            "type": "user_message",
            "project_id": project_id,
            "user_id": user_id,
            "message": message,
            "source_instance": self.instance_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self.redis_client.publish(self.MESSAGE_CHANNEL, json.dumps(cluster_message))
        return True

    async def get_project_users(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all connected users for a project across all instances"""

        if not self.redis_client:
            return []

        # Get all connection keys for the project
        pattern = f"websocket:connection:{project_id}:*"
        keys = await self.redis_client.keys(pattern)

        users = []
        for key in keys:
            try:
                connection_data = await self.redis_client.get(key)
                if connection_data:
                    users.append(json.loads(connection_data))
            except Exception as e:
                logger.warning(f"Failed to parse connection data for {key}: {e}")

        return users

    async def _listen_for_cluster_messages(self):
        """Background task to listen for Redis pub/sub messages"""

        if not self.pubsub:
            return

        try:
            async for message in self.pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    channel = message["channel"]

                    # Skip messages from this instance
                    if data.get("source_instance") == self.instance_id:
                        continue

                    if channel == self.MESSAGE_CHANNEL:
                        await self._handle_cluster_message(data)
                    elif channel == self.CONNECTION_CHANNEL:
                        await self._handle_connection_event(data)
                    elif channel == self.HEARTBEAT_CHANNEL:
                        await self._handle_heartbeat(data)

                except Exception as e:
                    logger.error(f"Failed to process cluster message: {e}")

        except Exception as e:
            logger.error(f"WebSocket cluster listener error: {e}")
            self.is_listening = False

    async def _handle_cluster_message(self, data: Dict[str, Any]):
        """Handle incoming cluster messages and forward to local connections"""

        message_type = data.get("type")

        if message_type == "project_broadcast":
            project_id = data.get("project_id")
            message = data.get("message")
            exclude_user = data.get("exclude_user")

            # Forward to local connections in this project
            if project_id in self.local_connections:
                # This would be handled by the main WebSocketConnectionManager
                # We'll add a callback mechanism for this
                await self._forward_to_local_connections(project_id, message, exclude_user)

        elif message_type == "user_message":
            project_id = data.get("project_id")
            user_id = data.get("user_id")
            message = data.get("message")

            # Forward to specific local user if connected
            if (
                project_id in self.local_connections
                and user_id in self.local_connections[project_id]
            ):
                await self._forward_to_local_user(project_id, user_id, message)

    async def _handle_connection_event(self, data: Dict[str, Any]):
        """Handle connection/disconnection events from other instances"""

        action = data.get("action")
        project_id = data.get("project_id")
        user_id = data.get("user_id")
        instance_id = data.get("instance_id")

        logger.debug(
            f"Connection event: {action} for user {user_id} "
            f"in project {project_id} from instance {instance_id}"
        )

    async def _handle_heartbeat(self, data: Dict[str, Any]):
        """Handle heartbeat messages from other instances"""
        instance_id = data.get("instance_id")
        timestamp = data.get("timestamp")

        # Could be used for instance health monitoring
        logger.debug(f"Heartbeat from instance {instance_id} at {timestamp}")

    async def _send_heartbeat(self):
        """Send periodic heartbeat to indicate this instance is alive"""

        while self.is_listening and self.redis_client:
            try:
                heartbeat_data = {
                    "instance_id": self.instance_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "connections": sum(len(users) for users in self.local_connections.values()),
                }

                await self.redis_client.publish(self.HEARTBEAT_CHANNEL, json.dumps(heartbeat_data))

                # Send heartbeat every 30 seconds
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Failed to send heartbeat: {e}")
                await asyncio.sleep(10)  # Retry after 10 seconds

    async def _forward_to_local_connections(
        self,
        project_id: str,
        message: Dict[str, Any],
        exclude_user: Optional[str] = None,
    ):
        """Forward cluster message to local WebSocket connections"""

        # This will be called by the main WebSocketConnectionManager
        # We'll add a callback mechanism to integrate with the existing system

    async def _forward_to_local_user(self, project_id: str, user_id: str, message: Dict[str, Any]):
        """Forward cluster message to a specific local user"""

        # This will be called by the main WebSocketConnectionManager
        # We'll add a callback mechanism to integrate with the existing system

    async def cleanup(self):
        """Clean up Redis connections and stop background tasks"""

        self.is_listening = False

        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()

        if self.redis_client:
            await self.redis_client.close()

        logger.info(f"WebSocket clustering cleaned up for instance {self.instance_id}")


# Global cluster manager instance
cluster_manager = WebSocketClusterManager()
