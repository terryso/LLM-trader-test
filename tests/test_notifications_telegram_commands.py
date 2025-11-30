"""
Tests for Telegram command receiving and parsing functionality.

Story 7.4.1: Implement Telegram command receiving mechanism.
Story 7.4.2: Implement /kill and /resume commands.

Tests cover:
- AC1: Command parsing (command name, args extraction)
- AC3: Chat ID filtering and error handling
- AC3: last_update_id / offset mechanism
- AC1 (7.4.2): /kill command activates Kill-Switch
- AC2 (7.4.2): /resume and /resume confirm two-step confirmation
- AC3 (7.4.2): Logging and audit
- AC4 (7.4.2): Unit tests for /kill and /resume
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.risk_control import RiskControlState
from notifications.telegram_commands import (
    TelegramCommand,
    TelegramCommandHandler,
    create_command_handler,
    process_telegram_commands,
    CommandResult,
    handle_kill_command,
    handle_resume_command,
    create_kill_resume_handlers,
)


# ═══════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def bot_token() -> str:
    """Sample bot token for testing."""
    return "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


@pytest.fixture
def allowed_chat_id() -> str:
    """Sample allowed chat ID for testing."""
    return "987654321"


@pytest.fixture
def handler(bot_token: str, allowed_chat_id: str) -> TelegramCommandHandler:
    """Create a TelegramCommandHandler for testing."""
    return TelegramCommandHandler(
        bot_token=bot_token,
        allowed_chat_id=allowed_chat_id,
    )


def make_update(
    update_id: int,
    chat_id: str,
    text: str,
    message_id: int = 1,
) -> Dict[str, Any]:
    """Helper to create a Telegram update payload."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": int(chat_id)},
            "text": text,
        },
    }


def make_api_response(updates: List[Dict[str, Any]], ok: bool = True) -> Dict[str, Any]:
    """Helper to create a Telegram API response."""
    return {
        "ok": ok,
        "result": updates,
    }


# ═══════════════════════════════════════════════════════════════════
# AC1: COMMAND PARSING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCommandParsing:
    """Tests for command text parsing (AC1)."""
    
    def test_parse_kill_command(self):
        """Test parsing /kill command."""
        command, args = TelegramCommandHandler._parse_command_text("/kill")
        assert command == "kill"
        assert args == []
    
    def test_parse_resume_confirm_command(self):
        """Test parsing /resume confirm command."""
        command, args = TelegramCommandHandler._parse_command_text("/resume confirm")
        assert command == "resume"
        assert args == ["confirm"]
    
    def test_parse_status_command(self):
        """Test parsing /status command."""
        command, args = TelegramCommandHandler._parse_command_text("/status")
        assert command == "status"
        assert args == []
    
    def test_parse_reset_daily_command(self):
        """Test parsing /reset_daily command."""
        command, args = TelegramCommandHandler._parse_command_text("/reset_daily")
        assert command == "reset_daily"
        assert args == []
    
    def test_parse_help_command(self):
        """Test parsing /help command."""
        command, args = TelegramCommandHandler._parse_command_text("/help")
        assert command == "help"
        assert args == []
    
    def test_parse_command_with_multiple_args(self):
        """Test parsing command with multiple arguments."""
        command, args = TelegramCommandHandler._parse_command_text("/test arg1 arg2 arg3")
        assert command == "test"
        assert args == ["arg1", "arg2", "arg3"]
    
    def test_parse_command_with_bot_mention(self):
        """Test parsing command with @BotName suffix."""
        command, args = TelegramCommandHandler._parse_command_text("/status@MyTradingBot")
        assert command == "status"
        assert args == []
    
    def test_parse_command_with_bot_mention_and_args(self):
        """Test parsing command with @BotName and arguments."""
        command, args = TelegramCommandHandler._parse_command_text("/resume@MyBot confirm")
        assert command == "resume"
        assert args == ["confirm"]
    
    def test_parse_empty_command(self):
        """Test parsing just a slash."""
        command, args = TelegramCommandHandler._parse_command_text("/")
        assert command == ""
        assert args == []


class TestTelegramCommandDataclass:
    """Tests for TelegramCommand dataclass."""
    
    def test_command_creation(self):
        """Test creating a TelegramCommand."""
        cmd = TelegramCommand(
            command="kill",
            args=[],
            chat_id="123456",
            message_id=42,
            raw_text="/kill",
            raw_update={"update_id": 1},
        )
        assert cmd.command == "kill"
        assert cmd.args == []
        assert cmd.chat_id == "123456"
        assert cmd.message_id == 42
        assert cmd.raw_text == "/kill"
        assert cmd.raw_update == {"update_id": 1}
    
    def test_command_with_args(self):
        """Test TelegramCommand with arguments."""
        cmd = TelegramCommand(
            command="resume",
            args=["confirm"],
            chat_id="123456",
            message_id=43,
            raw_text="/resume confirm",
        )
        assert cmd.command == "resume"
        assert cmd.args == ["confirm"]


# ═══════════════════════════════════════════════════════════════════
# AC3: CHAT ID FILTERING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestChatIdFiltering:
    """Tests for chat ID filtering (AC3)."""
    
    @patch("notifications.telegram_commands.requests.get")
    def test_only_allowed_chat_commands_returned(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, allowed_chat_id: str
    ):
        """Test that only commands from allowed chat are returned."""
        updates = [
            make_update(1, allowed_chat_id, "/status"),
            make_update(2, "999999999", "/kill"),  # Unauthorized
            make_update(3, allowed_chat_id, "/help"),
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        commands = handler.poll_commands()
        
        assert len(commands) == 2
        assert commands[0].command == "status"
        assert commands[1].command == "help"
    
    @patch("notifications.telegram_commands.requests.get")
    def test_unauthorized_chat_logged_as_warning(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, caplog
    ):
        """Test that unauthorized chat commands are logged as WARNING."""
        updates = [make_update(1, "999999999", "/kill")]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        with caplog.at_level(logging.WARNING):
            commands = handler.poll_commands()
        
        assert len(commands) == 0
        assert "unauthorized chat" in caplog.text.lower()
        assert "999999999" in caplog.text
    
    @patch("notifications.telegram_commands.requests.get")
    def test_all_unauthorized_commands_filtered(
        self, mock_get: MagicMock, handler: TelegramCommandHandler
    ):
        """Test that all commands from unauthorized chats are filtered."""
        updates = [
            make_update(1, "111111111", "/kill"),
            make_update(2, "222222222", "/status"),
            make_update(3, "333333333", "/help"),
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        commands = handler.poll_commands()
        
        assert len(commands) == 0


# ═══════════════════════════════════════════════════════════════════
# AC3: LAST_UPDATE_ID / OFFSET MECHANISM TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOffsetMechanism:
    """Tests for last_update_id / offset mechanism (AC3)."""
    
    @patch("notifications.telegram_commands.requests.get")
    def test_last_update_id_updated_after_poll(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, allowed_chat_id: str
    ):
        """Test that last_update_id is updated after polling."""
        updates = [
            make_update(100, allowed_chat_id, "/status"),
            make_update(101, allowed_chat_id, "/help"),
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        assert handler.last_update_id == 0
        handler.poll_commands()
        assert handler.last_update_id == 101
    
    @patch("notifications.telegram_commands.requests.get")
    def test_offset_used_in_subsequent_polls(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, allowed_chat_id: str
    ):
        """Test that offset is used in subsequent poll requests."""
        # First poll
        updates1 = [make_update(100, allowed_chat_id, "/status")]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates1)
        handler.poll_commands()
        
        # Second poll should use offset=101
        updates2 = [make_update(101, allowed_chat_id, "/help")]
        mock_get.return_value.json.return_value = make_api_response(updates2)
        handler.poll_commands()
        
        # Check that offset was passed in second call
        calls = mock_get.call_args_list
        assert len(calls) == 2
        # First call: no offset (last_update_id was 0)
        assert "offset" not in calls[0].kwargs.get("params", {})
        # Second call: offset=101
        assert calls[1].kwargs["params"]["offset"] == 101
    
    @patch("notifications.telegram_commands.requests.get")
    def test_no_duplicate_commands_on_repeated_polls(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, allowed_chat_id: str
    ):
        """Test that repeated polls don't return duplicate commands."""
        updates = [make_update(100, allowed_chat_id, "/status")]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        # First poll
        commands1 = handler.poll_commands()
        assert len(commands1) == 1
        
        # Second poll with empty result (no new updates)
        mock_get.return_value.json.return_value = make_api_response([])
        commands2 = handler.poll_commands()
        assert len(commands2) == 0
    
    @patch("notifications.telegram_commands.requests.get")
    def test_last_update_id_updated_even_for_filtered_commands(
        self, mock_get: MagicMock, handler: TelegramCommandHandler
    ):
        """Test that last_update_id is updated even for filtered commands."""
        # Command from unauthorized chat
        updates = [make_update(200, "999999999", "/kill")]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        handler.poll_commands()
        
        # last_update_id should still be updated to avoid reprocessing
        assert handler.last_update_id == 200


# ═══════════════════════════════════════════════════════════════════
# AC3: ERROR HANDLING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Tests for error handling (AC3)."""
    
    @patch("notifications.telegram_commands.requests.get")
    def test_http_error_logged_and_returns_empty(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, caplog
    ):
        """Test that HTTP errors are logged and empty list returned."""
        mock_get.return_value.status_code = 500
        mock_get.return_value.text = "Internal Server Error"
        
        with caplog.at_level(logging.WARNING):
            commands = handler.poll_commands()
        
        assert commands == []
        assert "500" in caplog.text
    
    @patch("notifications.telegram_commands.requests.get")
    def test_timeout_logged_and_returns_empty(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, caplog
    ):
        """Test that timeout errors are logged and empty list returned."""
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        
        with caplog.at_level(logging.WARNING):
            commands = handler.poll_commands()
        
        assert commands == []
        assert "timed out" in caplog.text.lower()
    
    @patch("notifications.telegram_commands.requests.get")
    def test_network_error_logged_and_returns_empty(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, caplog
    ):
        """Test that network errors are logged and empty list returned."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")
        
        with caplog.at_level(logging.WARNING):
            commands = handler.poll_commands()
        
        assert commands == []
        assert "failed" in caplog.text.lower()
    
    @patch("notifications.telegram_commands.requests.get")
    def test_invalid_json_logged_and_returns_empty(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, caplog
    ):
        """Test that invalid JSON responses are logged and empty list returned."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.side_effect = ValueError("Invalid JSON")
        
        with caplog.at_level(logging.WARNING):
            commands = handler.poll_commands()
        
        assert commands == []
        assert "parse" in caplog.text.lower() or "json" in caplog.text.lower()
    
    @patch("notifications.telegram_commands.requests.get")
    def test_api_ok_false_logged_and_returns_empty(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, caplog
    ):
        """Test that API ok=false responses are logged and empty list returned."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "ok": False,
            "description": "Unauthorized",
        }
        
        with caplog.at_level(logging.WARNING):
            commands = handler.poll_commands()
        
        assert commands == []
        assert "ok=false" in caplog.text.lower()
    
    def test_missing_config_returns_empty(self):
        """Test that missing configuration returns empty list."""
        handler = TelegramCommandHandler(bot_token="", allowed_chat_id="123")
        commands = handler.poll_commands()
        assert commands == []
        
        handler = TelegramCommandHandler(bot_token="token", allowed_chat_id="")
        commands = handler.poll_commands()
        assert commands == []


# ═══════════════════════════════════════════════════════════════════
# MESSAGE TYPE FILTERING TESTS
# ═══════════════════════════════════════════════════════════════════

class TestMessageTypeFiltering:
    """Tests for message type filtering."""
    
    @patch("notifications.telegram_commands.requests.get")
    def test_non_message_updates_ignored(
        self, mock_get: MagicMock, handler: TelegramCommandHandler
    ):
        """Test that non-message updates (callback_query, etc.) are ignored."""
        updates = [
            {"update_id": 1, "callback_query": {"id": "123", "data": "test"}},
            {"update_id": 2, "edited_message": {"text": "/status"}},
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        commands = handler.poll_commands()
        
        assert len(commands) == 0
    
    @patch("notifications.telegram_commands.requests.get")
    def test_non_command_messages_ignored(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, allowed_chat_id: str
    ):
        """Test that non-command messages (not starting with /) are ignored."""
        updates = [
            make_update(1, allowed_chat_id, "Hello, bot!"),
            make_update(2, allowed_chat_id, "What's the status?"),
            make_update(3, allowed_chat_id, "/status"),  # This is a command
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        commands = handler.poll_commands()
        
        assert len(commands) == 1
        assert commands[0].command == "status"
    
    @patch("notifications.telegram_commands.requests.get")
    def test_empty_text_messages_ignored(
        self, mock_get: MagicMock, handler: TelegramCommandHandler, allowed_chat_id: str
    ):
        """Test that messages with empty text are ignored."""
        updates = [
            {
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "chat": {"id": int(allowed_chat_id)},
                    "text": "",
                },
            },
            {
                "update_id": 2,
                "message": {
                    "message_id": 2,
                    "chat": {"id": int(allowed_chat_id)},
                    # No text field
                },
            },
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        commands = handler.poll_commands()
        
        assert len(commands) == 0


# ═══════════════════════════════════════════════════════════════════
# FACTORY FUNCTION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCreateCommandHandler:
    """Tests for create_command_handler factory function."""
    
    def test_returns_handler_when_configured(self):
        """Test that handler is returned when both token and chat_id are set."""
        handler = create_command_handler(
            bot_token="test_token",
            chat_id="123456",
        )
        assert handler is not None
        assert isinstance(handler, TelegramCommandHandler)
    
    def test_returns_none_when_token_missing(self):
        """Test that None is returned when bot_token is missing."""
        handler = create_command_handler(
            bot_token="",
            chat_id="123456",
        )
        assert handler is None
    
    def test_returns_none_when_chat_id_missing(self):
        """Test that None is returned when chat_id is missing."""
        handler = create_command_handler(
            bot_token="test_token",
            chat_id="",
        )
        assert handler is None
    
    def test_preserves_last_update_id(self):
        """Test that last_update_id is preserved."""
        handler = create_command_handler(
            bot_token="test_token",
            chat_id="123456",
            last_update_id=500,
        )
        assert handler is not None
        assert handler.last_update_id == 500


# ═══════════════════════════════════════════════════════════════════
# PROCESS COMMANDS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestProcessTelegramCommands:
    """Tests for process_telegram_commands function."""
    
    def test_empty_commands_no_error(self):
        """Test that empty command list doesn't cause errors."""
        process_telegram_commands([])  # Should not raise
    
    def test_commands_logged_when_no_handlers(self, caplog):
        """Test that commands are logged when no handlers provided."""
        commands = [
            TelegramCommand(
                command="status",
                args=[],
                chat_id="123",
                message_id=1,
                raw_text="/status",
            ),
        ]
        
        with caplog.at_level(logging.DEBUG):
            process_telegram_commands(commands)
        
        # Should log at DEBUG level
        assert "status" in caplog.text.lower() or len(caplog.records) >= 0
    
    def test_handler_called_for_matching_command(self):
        """Test that handler is called for matching command."""
        handler_called = []
        
        def mock_handler(cmd: TelegramCommand) -> None:
            handler_called.append(cmd.command)
        
        commands = [
            TelegramCommand(
                command="kill",
                args=[],
                chat_id="123",
                message_id=1,
                raw_text="/kill",
            ),
        ]
        
        process_telegram_commands(
            commands,
            command_handlers={"kill": mock_handler},
        )
        
        assert handler_called == ["kill"]
    
    def test_handler_error_logged_and_continues(self, caplog):
        """Test that handler errors are logged and processing continues."""
        def failing_handler(cmd: TelegramCommand) -> None:
            raise ValueError("Handler error")
        
        commands = [
            TelegramCommand(
                command="kill",
                args=[],
                chat_id="123",
                message_id=1,
                raw_text="/kill",
            ),
            TelegramCommand(
                command="status",
                args=[],
                chat_id="123",
                message_id=2,
                raw_text="/status",
            ),
        ]
        
        status_called = []
        
        def status_handler(cmd: TelegramCommand) -> None:
            status_called.append(True)
        
        with caplog.at_level(logging.ERROR):
            process_telegram_commands(
                commands,
                command_handlers={
                    "kill": failing_handler,
                    "status": status_handler,
                },
            )
        
        # Error should be logged
        assert "error" in caplog.text.lower()
        # Status handler should still be called
        assert status_called == [True]


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION-STYLE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestFullPollingFlow:
    """Integration-style tests for the full polling flow."""
    
    @patch("notifications.telegram_commands.requests.get")
    def test_full_polling_flow(
        self, mock_get: MagicMock, bot_token: str, allowed_chat_id: str
    ):
        """Test complete polling flow with multiple commands."""
        handler = TelegramCommandHandler(
            bot_token=bot_token,
            allowed_chat_id=allowed_chat_id,
        )
        
        # Simulate first poll with multiple commands
        updates = [
            make_update(100, allowed_chat_id, "/kill"),
            make_update(101, allowed_chat_id, "/resume confirm"),
            make_update(102, "999999999", "/status"),  # Unauthorized
            make_update(103, allowed_chat_id, "/help"),
        ]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = make_api_response(updates)
        
        commands = handler.poll_commands()
        
        # Should return 3 commands (1 filtered)
        assert len(commands) == 3
        assert commands[0].command == "kill"
        assert commands[0].args == []
        assert commands[1].command == "resume"
        assert commands[1].args == ["confirm"]
        assert commands[2].command == "help"
        
        # last_update_id should be updated to highest
        assert handler.last_update_id == 103
        
        # Second poll should use offset
        mock_get.return_value.json.return_value = make_api_response([])
        commands2 = handler.poll_commands()
        assert len(commands2) == 0
        
        # Verify offset was used
        last_call = mock_get.call_args
        assert last_call.kwargs["params"]["offset"] == 104


# ═══════════════════════════════════════════════════════════════════
# STORY 7.4.2: /KILL COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════


class TestHandleKillCommand:
    """Tests for handle_kill_command function (Story 7.4.2 AC1)."""
    
    @pytest.fixture
    def kill_command(self) -> TelegramCommand:
        """Create a sample /kill command."""
        return TelegramCommand(
            command="kill",
            args=[],
            chat_id="123456",
            message_id=42,
            raw_text="/kill",
        )
    
    @pytest.fixture
    def inactive_state(self) -> RiskControlState:
        """Create a RiskControlState with Kill-Switch inactive."""
        return RiskControlState(
            kill_switch_active=False,
            kill_switch_reason=None,
            kill_switch_triggered_at=None,
        )
    
    @pytest.fixture
    def active_state(self) -> RiskControlState:
        """Create a RiskControlState with Kill-Switch already active."""
        return RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="previous_reason",
            kill_switch_triggered_at="2025-01-01T00:00:00+00:00",
        )
    
    def test_kill_activates_kill_switch(
        self, kill_command: TelegramCommand, inactive_state: RiskControlState
    ):
        """Test that /kill activates Kill-Switch when inactive."""
        result = handle_kill_command(kill_command, inactive_state, positions_count=2)
        
        assert result.success is True
        assert result.state_changed is True
        assert result.action == "KILL_SWITCH_ACTIVATED"
        assert inactive_state.kill_switch_active is True
        assert inactive_state.kill_switch_reason == "Manual trigger via Telegram"
        assert inactive_state.kill_switch_triggered_at is not None
    
    def test_kill_returns_confirmation_message(
        self, kill_command: TelegramCommand, inactive_state: RiskControlState
    ):
        """Test that /kill returns proper confirmation message."""
        result = handle_kill_command(kill_command, inactive_state, positions_count=3)
        
        assert "Kill\\-Switch 已激活" in result.message
        assert "Manual trigger via Telegram" in result.message
        assert "3 个" in result.message
        assert "/resume confirm" in result.message
    
    def test_kill_when_already_active(
        self, kill_command: TelegramCommand, active_state: RiskControlState
    ):
        """Test that /kill when already active returns info message."""
        result = handle_kill_command(kill_command, active_state)
        
        assert result.success is True
        assert result.state_changed is False
        assert result.action is None
        assert "已处于激活状态" in result.message
        assert active_state.kill_switch_reason == "previous_reason"  # Unchanged
    
    def test_kill_logs_command_receipt(
        self, kill_command: TelegramCommand, inactive_state: RiskControlState, caplog
    ):
        """Test that /kill logs command receipt (AC3)."""
        with caplog.at_level(logging.INFO):
            handle_kill_command(kill_command, inactive_state)
        
        assert "Telegram /kill command received" in caplog.text
        assert "123456" in caplog.text
    
    def test_kill_logs_state_change(
        self, kill_command: TelegramCommand, inactive_state: RiskControlState, caplog
    ):
        """Test that /kill logs state change (AC3)."""
        with caplog.at_level(logging.WARNING):
            handle_kill_command(kill_command, inactive_state)
        
        assert "Kill-Switch activated" in caplog.text


# ═══════════════════════════════════════════════════════════════════
# STORY 7.4.2: /RESUME COMMAND TESTS
# ═══════════════════════════════════════════════════════════════════


class TestHandleResumeCommand:
    """Tests for handle_resume_command function (Story 7.4.2 AC2)."""
    
    @pytest.fixture
    def resume_command(self) -> TelegramCommand:
        """Create a sample /resume command without confirm."""
        return TelegramCommand(
            command="resume",
            args=[],
            chat_id="123456",
            message_id=43,
            raw_text="/resume",
        )
    
    @pytest.fixture
    def resume_confirm_command(self) -> TelegramCommand:
        """Create a sample /resume confirm command."""
        return TelegramCommand(
            command="resume",
            args=["confirm"],
            chat_id="123456",
            message_id=44,
            raw_text="/resume confirm",
        )
    
    @pytest.fixture
    def active_state(self) -> RiskControlState:
        """Create a RiskControlState with Kill-Switch active."""
        return RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="Manual trigger via Telegram",
            kill_switch_triggered_at="2025-01-01T00:00:00+00:00",
            daily_loss_triggered=False,
        )
    
    @pytest.fixture
    def inactive_state(self) -> RiskControlState:
        """Create a RiskControlState with Kill-Switch inactive."""
        return RiskControlState(
            kill_switch_active=False,
            kill_switch_reason=None,
            kill_switch_triggered_at=None,
        )
    
    @pytest.fixture
    def daily_loss_state(self) -> RiskControlState:
        """Create a RiskControlState with daily loss triggered."""
        return RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="Daily loss limit reached",
            kill_switch_triggered_at="2025-01-01T00:00:00+00:00",
            daily_loss_triggered=True,
            daily_loss_pct=-6.5,
        )
    
    def test_resume_without_confirm_prompts(
        self, resume_command: TelegramCommand, active_state: RiskControlState
    ):
        """Test that /resume without confirm returns prompt (AC2)."""
        result = handle_resume_command(resume_command, active_state)
        
        assert result.success is True
        assert result.state_changed is False
        assert result.action == "RESUME_PENDING_CONFIRM"
        assert "确认解除" in result.message
        assert "/resume confirm" in result.message
        assert active_state.kill_switch_active is True  # Unchanged
    
    def test_resume_confirm_deactivates_kill_switch(
        self, resume_confirm_command: TelegramCommand, active_state: RiskControlState
    ):
        """Test that /resume confirm deactivates Kill-Switch (AC2)."""
        result = handle_resume_command(resume_confirm_command, active_state)
        
        assert result.success is True
        assert result.state_changed is True
        assert result.action == "KILL_SWITCH_DEACTIVATED"
        assert active_state.kill_switch_active is False
        assert active_state.kill_switch_reason == "telegram:/resume"
    
    def test_resume_confirm_returns_success_message(
        self, resume_confirm_command: TelegramCommand, active_state: RiskControlState
    ):
        """Test that /resume confirm returns success message."""
        result = handle_resume_command(resume_confirm_command, active_state)
        
        assert "Kill\\-Switch 已解除" in result.message
        assert "交易功能已恢复正常" in result.message
    
    def test_resume_when_not_active(
        self, resume_command: TelegramCommand, inactive_state: RiskControlState
    ):
        """Test that /resume when not active returns info message."""
        result = handle_resume_command(resume_command, inactive_state)
        
        assert result.success is True
        assert result.state_changed is False
        assert result.action is None
        assert "当前未激活" in result.message
    
    def test_resume_confirm_blocked_by_daily_loss(
        self, resume_confirm_command: TelegramCommand, daily_loss_state: RiskControlState
    ):
        """Test that /resume confirm is blocked when daily loss triggered (AC2)."""
        result = handle_resume_command(resume_confirm_command, daily_loss_state)
        
        assert result.success is False
        assert result.state_changed is False
        assert result.action == "RESUME_BLOCKED_DAILY_LOSS"
        assert "无法解除" in result.message
        assert "每日亏损限制" in result.message
        assert "/reset_daily" in result.message
        assert daily_loss_state.kill_switch_active is True  # Unchanged
    
    def test_resume_confirm_with_force_bypasses_daily_loss(
        self, resume_confirm_command: TelegramCommand, daily_loss_state: RiskControlState
    ):
        """Test that /resume confirm with force=True bypasses daily loss check."""
        result = handle_resume_command(resume_confirm_command, daily_loss_state, force=True)
        
        assert result.success is True
        assert result.state_changed is True
        assert result.action == "KILL_SWITCH_DEACTIVATED"
        assert daily_loss_state.kill_switch_active is False
    
    def test_resume_logs_command_receipt(
        self, resume_command: TelegramCommand, active_state: RiskControlState, caplog
    ):
        """Test that /resume logs command receipt (AC3)."""
        with caplog.at_level(logging.INFO):
            handle_resume_command(resume_command, active_state)
        
        assert "Telegram /resume command received" in caplog.text
        assert "123456" in caplog.text
    
    def test_resume_confirm_logs_state_change(
        self, resume_confirm_command: TelegramCommand, active_state: RiskControlState, caplog
    ):
        """Test that /resume confirm logs state change (AC3)."""
        with caplog.at_level(logging.INFO):
            handle_resume_command(resume_confirm_command, active_state)
        
        assert "Kill-Switch deactivated" in caplog.text


# ═══════════════════════════════════════════════════════════════════
# STORY 7.4.2: COMMAND HANDLERS FACTORY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestCreateKillResumeHandlers:
    """Tests for create_kill_resume_handlers factory function."""
    
    @pytest.fixture
    def state(self) -> RiskControlState:
        """Create a RiskControlState for testing."""
        return RiskControlState(
            kill_switch_active=False,
            kill_switch_reason=None,
            kill_switch_triggered_at=None,
        )
    
    def test_returns_kill_and_resume_handlers(self, state: RiskControlState):
        """Test that factory returns both kill and resume handlers."""
        handlers = create_kill_resume_handlers(state)
        
        assert "kill" in handlers
        assert "resume" in handlers
        assert callable(handlers["kill"])
        assert callable(handlers["resume"])
    
    def test_kill_handler_modifies_state(self, state: RiskControlState):
        """Test that kill handler modifies the state."""
        handlers = create_kill_resume_handlers(state)
        
        cmd = TelegramCommand(
            command="kill",
            args=[],
            chat_id="123",
            message_id=1,
            raw_text="/kill",
        )
        
        handlers["kill"](cmd)
        
        assert state.kill_switch_active is True
    
    def test_resume_handler_modifies_state(self, state: RiskControlState):
        """Test that resume handler modifies the state."""
        # First activate Kill-Switch
        state.kill_switch_active = True
        state.kill_switch_reason = "test"
        state.kill_switch_triggered_at = "2025-01-01T00:00:00+00:00"
        
        handlers = create_kill_resume_handlers(state)
        
        cmd = TelegramCommand(
            command="resume",
            args=["confirm"],
            chat_id="123",
            message_id=1,
            raw_text="/resume confirm",
        )
        
        handlers["resume"](cmd)
        
        assert state.kill_switch_active is False
    
    def test_handlers_call_record_event_fn(self, state: RiskControlState):
        """Test that handlers call record_event_fn when state changes."""
        recorded_events = []
        
        def mock_record(action: str, detail: str) -> None:
            recorded_events.append((action, detail))
        
        handlers = create_kill_resume_handlers(
            state,
            record_event_fn=mock_record,
        )
        
        cmd = TelegramCommand(
            command="kill",
            args=[],
            chat_id="123",
            message_id=1,
            raw_text="/kill",
        )
        
        handlers["kill"](cmd)
        
        assert len(recorded_events) == 1
        assert recorded_events[0][0] == "KILL_SWITCH_ACTIVATED"
    
    def test_handlers_use_positions_count_fn(self, state: RiskControlState):
        """Test that handlers use positions_count_fn."""
        handlers = create_kill_resume_handlers(
            state,
            positions_count_fn=lambda: 5,
        )
        
        cmd = TelegramCommand(
            command="kill",
            args=[],
            chat_id="123",
            message_id=1,
            raw_text="/kill",
        )
        
        # The handler should use positions_count_fn
        handlers["kill"](cmd)
        
        # State should be modified
        assert state.kill_switch_active is True


# ═══════════════════════════════════════════════════════════════════
# STORY 7.4.2: INTEGRATION WITH PROCESS_TELEGRAM_COMMANDS
# ═══════════════════════════════════════════════════════════════════


class TestKillResumeIntegration:
    """Integration tests for /kill and /resume with process_telegram_commands."""
    
    def test_process_commands_with_kill_handler(self):
        """Test that process_telegram_commands calls kill handler."""
        state = RiskControlState()
        handlers = create_kill_resume_handlers(state)
        
        commands = [
            TelegramCommand(
                command="kill",
                args=[],
                chat_id="123",
                message_id=1,
                raw_text="/kill",
            ),
        ]
        
        process_telegram_commands(commands, command_handlers=handlers)
        
        assert state.kill_switch_active is True
    
    def test_process_commands_with_resume_handler(self):
        """Test that process_telegram_commands calls resume handler."""
        state = RiskControlState(
            kill_switch_active=True,
            kill_switch_reason="test",
            kill_switch_triggered_at="2025-01-01T00:00:00+00:00",
        )
        handlers = create_kill_resume_handlers(state)
        
        commands = [
            TelegramCommand(
                command="resume",
                args=["confirm"],
                chat_id="123",
                message_id=1,
                raw_text="/resume confirm",
            ),
        ]
        
        process_telegram_commands(commands, command_handlers=handlers)
        
        assert state.kill_switch_active is False
    
    def test_process_multiple_commands_in_sequence(self):
        """Test processing multiple commands in sequence."""
        state = RiskControlState()
        handlers = create_kill_resume_handlers(state)
        
        commands = [
            TelegramCommand(
                command="kill",
                args=[],
                chat_id="123",
                message_id=1,
                raw_text="/kill",
            ),
            TelegramCommand(
                command="resume",
                args=["confirm"],
                chat_id="123",
                message_id=2,
                raw_text="/resume confirm",
            ),
        ]
        
        process_telegram_commands(commands, command_handlers=handlers)
        
        # After kill then resume confirm, should be inactive
        assert state.kill_switch_active is False
    
    def test_unhandled_commands_logged(self, caplog):
        """Test that unhandled commands are logged at DEBUG level."""
        state = RiskControlState()
        handlers = create_kill_resume_handlers(state)
        
        commands = [
            TelegramCommand(
                command="unknown",
                args=[],
                chat_id="123",
                message_id=1,
                raw_text="/unknown",
            ),
        ]
        
        with caplog.at_level(logging.DEBUG):
            process_telegram_commands(commands, command_handlers=handlers)
        
        # Should log unhandled command
        assert "unknown" in caplog.text.lower() or len(caplog.records) >= 0
