"""
Unit Tests for WebSocket Clustering Module

Tests the Redis-based clustering functionality that enables
WebSocket connections to work across multiple server instances.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from websocket_clustering import WebSocketClusterManager


@pytest.fixture
def cluster_manager():
    """Create a WebSocketClusterManager instance for testing"""
    return WebSocketClusterManager()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client"""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock()
    redis_mock.publish = AsyncMock()
    redis_mock.setex = AsyncMock()
    redis_mock.delete = AsyncMock()
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.get = AsyncMock(return_value=None)

    # Mock pubsub - use regular Mock for pubsub() method so it doesn't return a coroutine
    pubsub_mock = AsyncMock()
    pubsub_mock.subscribe = AsyncMock()
    pubsub_mock.listen = AsyncMock()
    redis_mock.pubsub = MagicMock(return_value=pubsub_mock)

    return redis_mock, pubsub_mock


@pytest.mark.asyncio
class TestWebSocketClusterManager:
    """Test suite for WebSocket clustering functionality"""

    async def test_initialization_success(self, cluster_manager, mock_redis):
        """Test successful cluster manager initialization"""
        redis_mock, pubsub_mock = mock_redis

        with patch("websocket_clustering.redis.Redis", return_value=redis_mock):
            with patch("websocket_clustering.get_redis_client") as mock_get_redis:
                # Mock the sync Redis client for connection info
                sync_redis_mock = MagicMock()
                sync_redis_mock._connection_pool.connection_kwargs = {
                    "host": "localhost",
                    "port": 6379,
                    "db": 0,
                }
                mock_get_redis.return_value = sync_redis_mock

                await cluster_manager.initialize()

                # Verify Redis connection was established
                redis_mock.ping.assert_called_once()

                # Verify pub/sub subscription
                pubsub_mock.subscribe.assert_called_once_with(
                    cluster_manager.MESSAGE_CHANNEL,
                    cluster_manager.CONNECTION_CHANNEL,
                    cluster_manager.HEARTBEAT_CHANNEL,
                )

                assert cluster_manager.is_listening is True
                assert cluster_manager.redis_client is not None

    async def test_initialization_failure(self, cluster_manager):
        """Test cluster manager initialization failure"""
        with patch(
            "websocket_clustering.redis.Redis",
            side_effect=Exception("Redis unavailable"),
        ):
            await cluster_manager.initialize()

            assert cluster_manager.is_listening is False
            assert cluster_manager.redis_client is None

    async def test_register_connection(self, cluster_manager, mock_redis):
        """Test registering a WebSocket connection with the cluster"""
        redis_mock, _ = mock_redis
        cluster_manager.redis_client = redis_mock

        project_id = "test-project"
        user_id = "user123"
        websocket_id = "ws456"

        await cluster_manager.register_connection(project_id, user_id, websocket_id)

        # Verify local storage
        assert project_id in cluster_manager.local_connections
        assert user_id in cluster_manager.local_connections[project_id]

        connection_data = cluster_manager.local_connections[project_id][user_id]
        assert connection_data["websocket_id"] == websocket_id
        assert connection_data["instance_id"] == cluster_manager.instance_id

        # Verify Redis operations
        redis_mock.publish.assert_called_once()
        redis_mock.setex.assert_called_once()

    async def test_unregister_connection(self, cluster_manager, mock_redis):
        """Test unregistering a WebSocket connection from the cluster"""
        redis_mock, _ = mock_redis
        cluster_manager.redis_client = redis_mock

        project_id = "test-project"
        user_id = "user123"
        websocket_id = "ws456"

        # First register a connection
        await cluster_manager.register_connection(project_id, user_id, websocket_id)

        # Reset call counts
        redis_mock.reset_mock()

        # Then unregister it
        await cluster_manager.unregister_connection(project_id, user_id)

        # Verify local removal
        assert (
            project_id not in cluster_manager.local_connections
            or user_id not in cluster_manager.local_connections.get(project_id, {})
        )

        # Verify Redis operations
        redis_mock.publish.assert_called_once()
        redis_mock.delete.assert_called_once()

    async def test_broadcast_to_project(self, cluster_manager, mock_redis):
        """Test broadcasting a message to all users in a project"""
        redis_mock, _ = mock_redis
        cluster_manager.redis_client = redis_mock

        project_id = "test-project"
        message = {"type": "annotation_update", "data": "test"}
        exclude_user = "user456"

        await cluster_manager.broadcast_to_project(project_id, message, exclude_user)

        # Verify Redis publish was called
        redis_mock.publish.assert_called_once()

        # Verify message structure
        published_args = redis_mock.publish.call_args[0]
        channel = published_args[0]
        message_data = json.loads(published_args[1])

        assert channel == cluster_manager.MESSAGE_CHANNEL
        assert message_data["type"] == "project_broadcast"
        assert message_data["project_id"] == project_id
        assert message_data["message"] == message
        assert message_data["exclude_user"] == exclude_user
        assert message_data["source_instance"] == cluster_manager.instance_id

    async def test_send_to_user(self, cluster_manager, mock_redis):
        """Test sending a message to a specific user"""
        redis_mock, _ = mock_redis
        cluster_manager.redis_client = redis_mock

        project_id = "test-project"
        user_id = "user123"
        message = {"type": "comment_notification", "data": "test"}

        result = await cluster_manager.send_to_user(project_id, user_id, message)

        assert result is True

        # Verify Redis publish was called
        redis_mock.publish.assert_called_once()

        # Verify message structure
        published_args = redis_mock.publish.call_args[0]
        channel = published_args[0]
        message_data = json.loads(published_args[1])

        assert channel == cluster_manager.MESSAGE_CHANNEL
        assert message_data["type"] == "user_message"
        assert message_data["project_id"] == project_id
        assert message_data["user_id"] == user_id
        assert message_data["message"] == message

    async def test_get_project_users(self, cluster_manager, mock_redis):
        """Test getting all connected users for a project across instances"""
        redis_mock, _ = mock_redis
        cluster_manager.redis_client = redis_mock

        project_id = "test-project"

        # Mock Redis keys and get responses
        mock_keys = [
            f"websocket:connection:{project_id}:user1",
            f"websocket:connection:{project_id}:user2",
        ]
        redis_mock.keys.return_value = mock_keys

        mock_connections = [
            json.dumps({"user_id": "user1", "instance_id": "instance1"}),
            json.dumps({"user_id": "user2", "instance_id": "instance2"}),
        ]
        redis_mock.get.side_effect = mock_connections

        users = await cluster_manager.get_project_users(project_id)

        assert len(users) == 2
        assert users[0]["user_id"] == "user1"
        assert users[1]["user_id"] == "user2"

        # Verify Redis operations
        redis_mock.keys.assert_called_once_with(f"websocket:connection:{project_id}:*")
        assert redis_mock.get.call_count == 2

    async def test_cluster_message_handling(self, cluster_manager):
        """Test handling of incoming cluster messages"""
        # Mock callback functions
        cluster_manager._forward_to_local_connections = AsyncMock()
        cluster_manager._forward_to_local_user = AsyncMock()

        # Set up local connections so the project_id check passes
        cluster_manager.local_connections = {"test-project": {"user123": MagicMock()}}

        # Test project broadcast message
        project_message = {
            "type": "project_broadcast",
            "project_id": "test-project",
            "message": {"type": "test"},
            "exclude_user": "user456",
            "source_instance": "other-instance",
        }

        await cluster_manager._handle_cluster_message(project_message)

        cluster_manager._forward_to_local_connections.assert_called_once_with(
            "test-project", {"type": "test"}, "user456"
        )

        # Test user message
        user_message = {
            "type": "user_message",
            "project_id": "test-project",
            "user_id": "user123",
            "message": {"type": "notification"},
            "source_instance": "other-instance",
        }

        await cluster_manager._handle_cluster_message(user_message)

        cluster_manager._forward_to_local_user.assert_called_once_with(
            "test-project", "user123", {"type": "notification"}
        )

    async def test_connection_event_handling(self, cluster_manager):
        """Test handling of connection events from other instances"""
        connection_event = {
            "action": "connect",
            "project_id": "test-project",
            "user_id": "user123",
            "instance_id": "other-instance",
        }

        # Should not raise any exceptions
        await cluster_manager._handle_connection_event(connection_event)

    async def test_heartbeat_handling(self, cluster_manager):
        """Test handling of heartbeat messages from other instances"""
        heartbeat = {
            "instance_id": "other-instance",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "connections": 5,
        }

        # Should not raise any exceptions
        await cluster_manager._handle_heartbeat(heartbeat)

    async def test_cleanup(self, cluster_manager, mock_redis):
        """Test cluster manager cleanup"""
        redis_mock, pubsub_mock = mock_redis
        cluster_manager.redis_client = redis_mock
        cluster_manager.pubsub = pubsub_mock
        cluster_manager.is_listening = True

        await cluster_manager.cleanup()

        assert cluster_manager.is_listening is False
        pubsub_mock.unsubscribe.assert_called_once()
        pubsub_mock.close.assert_called_once()
        redis_mock.close.assert_called_once()

    async def test_no_redis_graceful_degradation(self, cluster_manager):
        """Test that clustering gracefully degrades when Redis is unavailable"""
        # Don't initialize Redis client
        cluster_manager.redis_client = None

        # These should not raise exceptions
        await cluster_manager.register_connection("project", "user", "ws")
        await cluster_manager.unregister_connection("project", "user")
        await cluster_manager.broadcast_to_project("project", {"type": "test"})
        result = await cluster_manager.send_to_user("project", "user", {"type": "test"})
        users = await cluster_manager.get_project_users("project")

        assert result is False  # Can't send without Redis
        assert users == []  # No users without Redis


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
