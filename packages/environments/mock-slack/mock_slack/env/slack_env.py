"""Gymnasium environment for Slack tool-use RL training."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx

try:
    import gymnasium as gym
    from gymnasium import spaces
    HAS_GYM = True
except ImportError:
    HAS_GYM = False

from mock_slack.seed.generator import seed_database
from mock_slack.tasks import get_task, list_tasks
from mock_slack.models import reset_engine


def _start_server(host: str, port: int, db_path: str):
    """Start the FastAPI server in a background thread."""
    from mock_slack.server import create_app
    import uvicorn

    app = create_app(db_path=db_path, enable_mcp=False)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


if HAS_GYM:
    class SlackToolEnv(gym.Env):
        """Gymnasium environment for interacting with the Mock Slack API via tool calls.

        Usage:
            env = SlackToolEnv(task_name="slack-post-01", scenario="default")
            obs, info = env.reset()
            obs, reward, terminated, truncated, info = env.step({
                "tool_name": "chat_post_message",
                "tool_args": {"channel": "C01GENERAL", "text": "Hello world!"}
            })
        """

        metadata = {"render_modes": ["human"]}

        # API tool definitions: tool_name -> (method, path_template)
        TOOLS = {
            # Conversations
            "conversations_list": ("GET", "/api/conversations.list"),
            "conversations_info": ("GET", "/api/conversations.info"),
            "conversations_history": ("GET", "/api/conversations.history"),
            "conversations_replies": ("GET", "/api/conversations.replies"),
            "conversations_create": ("POST", "/api/conversations.create"),
            "conversations_archive": ("POST", "/api/conversations.archive"),
            "conversations_unarchive": ("POST", "/api/conversations.unarchive"),
            "conversations_rename": ("POST", "/api/conversations.rename"),
            "conversations_invite": ("POST", "/api/conversations.invite"),
            "conversations_kick": ("POST", "/api/conversations.kick"),
            "conversations_join": ("POST", "/api/conversations.join"),
            "conversations_leave": ("POST", "/api/conversations.leave"),
            "conversations_members": ("GET", "/api/conversations.members"),
            "conversations_set_purpose": ("POST", "/api/conversations.setPurpose"),
            "conversations_set_topic": ("POST", "/api/conversations.setTopic"),
            # Chat / Messages
            "chat_post_message": ("POST", "/api/chat.postMessage"),
            "chat_post_ephemeral": ("POST", "/api/chat.postEphemeral"),
            "chat_update": ("POST", "/api/chat.update"),
            "chat_delete": ("POST", "/api/chat.delete"),
            "chat_get_permalink": ("GET", "/api/chat.getPermalink"),
            # Users
            "users_list": ("GET", "/api/users.list"),
            "users_info": ("GET", "/api/users.info"),
            "users_lookup_by_email": ("GET", "/api/users.lookupByEmail"),
            "users_profile_get": ("GET", "/api/users.profile.get"),
            # Reactions
            "reactions_add": ("POST", "/api/reactions.add"),
            "reactions_remove": ("POST", "/api/reactions.remove"),
            "reactions_get": ("GET", "/api/reactions.get"),
            # Search
            "search_messages": ("GET", "/api/search.messages"),
            # Files
            "files_list": ("GET", "/api/files.list"),
            "files_info": ("GET", "/api/files.info"),
            "files_upload": ("POST", "/api/files.upload"),
            "files_delete": ("POST", "/api/files.delete"),
            # Pins
            "pins_add": ("POST", "/api/pins.add"),
            "pins_remove": ("POST", "/api/pins.remove"),
            "pins_list": ("GET", "/api/pins.list"),
            # Team / Auth
            "team_info": ("GET", "/api/team.info"),
            "auth_test": ("POST", "/api/auth.test"),
        }

        # Write operations that should trigger evaluation
        WRITE_TOOLS = {
            "conversations_create", "conversations_archive", "conversations_unarchive",
            "conversations_rename", "conversations_invite", "conversations_kick",
            "conversations_join", "conversations_leave", "conversations_set_purpose",
            "conversations_set_topic",
            "chat_post_message", "chat_post_ephemeral", "chat_update", "chat_delete",
            "reactions_add", "reactions_remove",
            "files_upload", "files_delete",
            "pins_add", "pins_remove",
        }

        def __init__(
            self,
            task_name: str = "slack-post-01",
            scenario: str | None = None,
            host: str = "0.0.0.0",
            port: int = 8098,
            db_path: str = "gym_slack.db",
            seed: int = 42,
            max_steps: int = 50,
            step_penalty: float = -0.01,
        ):
            super().__init__()

            self.task_name = task_name
            self.host = host
            self.port = port
            self.db_path = db_path
            self.seed_val = seed
            self.max_steps = max_steps
            self.step_penalty = step_penalty
            self.base_url = f"http://{host}:{port}"

            task = get_task(task_name)
            if not task:
                raise ValueError(f"Unknown task: {task_name}. Available: {list_tasks()}")
            self.task = task
            self.scenario = scenario or task.scenario

            # Spaces
            self.action_space = spaces.Dict({
                "tool_name": spaces.Text(min_length=1, max_length=100),
                "tool_args": spaces.Text(min_length=0, max_length=10000),
            })
            self.observation_space = spaces.Dict({
                "goal": spaces.Text(min_length=0, max_length=10000),
                "api_response": spaces.Text(min_length=0, max_length=100000),
                "step": spaces.Discrete(max_steps + 1),
            })

            self._server_thread = None
            self._step_count = 0
            self._client = None

        def reset(self, seed=None, options=None):
            """Reset environment: re-seed DB, start server, return initial observation."""
            if seed is not None:
                self.seed_val = seed

            # Reset DB
            reset_engine()
            import os
            if os.path.exists(self.db_path):
                os.unlink(self.db_path)

            seed_database(
                scenario=self.scenario,
                seed=self.seed_val,
                db_path=self.db_path,
            )

            # Start server if not running
            if self._server_thread is None or not self._server_thread.is_alive():
                reset_engine()  # Reset so server picks up new DB
                self._server_thread = threading.Thread(
                    target=_start_server,
                    args=(self.host, self.port, self.db_path),
                    daemon=True,
                )
                self._server_thread.start()
                self._wait_for_server()

            self._client = httpx.Client(base_url=self.base_url, timeout=30)
            self._step_count = 0

            # Reset action log
            self._client.post("/_admin/reset")

            obs = {
                "goal": self.task.instruction,
                "api_response": json.dumps({"status": "ready", "task": self.task_name}),
                "step": 0,
            }
            info = {
                "task_name": self.task_name,
                "scenario": self.scenario,
                "tools": list(self.TOOLS.keys()),
            }
            return obs, info

        def step(self, action: dict[str, Any]):
            """Execute a tool call and return observation."""
            self._step_count += 1

            tool_name = action.get("tool_name", "")
            tool_args_raw = action.get("tool_args", "{}")

            # Parse tool args
            if isinstance(tool_args_raw, str):
                try:
                    tool_args = json.loads(tool_args_raw)
                except json.JSONDecodeError:
                    tool_args = {}
            else:
                tool_args = tool_args_raw

            # Execute tool call
            api_response = self._execute_tool(tool_name, tool_args)

            # Check task completion
            reward = self.step_penalty  # Per-step penalty
            terminated = False
            truncated = self._step_count >= self.max_steps

            if truncated or self._should_evaluate(tool_name):
                state = self._client.get("/_admin/state").json()
                diff = self._client.get("/_admin/diff").json()
                log = self._client.get("/_admin/action_log").json().get("entries", [])

                task_reward, done = self.task.evaluate(state, diff, log)
                reward += task_reward
                terminated = done

            obs = {
                "goal": self.task.instruction,
                "api_response": json.dumps(api_response) if isinstance(api_response, dict) else str(api_response),
                "step": self._step_count,
            }
            info = {"tool_name": tool_name, "step": self._step_count}

            return obs, reward, terminated, truncated, info

        def _execute_tool(self, tool_name: str, args: dict) -> dict:
            """Execute an API tool call."""
            if tool_name not in self.TOOLS:
                return {"ok": False, "error": f"unknown_tool", "detail": f"Unknown tool: {tool_name}. Available: {list(self.TOOLS.keys())}"}

            method, path = self.TOOLS[tool_name]

            try:
                if method == "GET":
                    resp = self._client.get(path, params=args)
                elif method == "POST":
                    resp = self._client.post(path, json=args)
                elif method == "DELETE":
                    resp = self._client.delete(path, params=args)
                else:
                    return {"ok": False, "error": f"unsupported_method"}

                return resp.json()
            except Exception as e:
                return {"ok": False, "error": "request_failed", "detail": str(e)}

        def _should_evaluate(self, tool_name: str) -> bool:
            """Evaluate after write operations."""
            return tool_name in self.WRITE_TOOLS

        def _wait_for_server(self, timeout: float = 10.0):
            """Wait for the server to be ready."""
            start = time.time()
            while time.time() - start < timeout:
                try:
                    resp = httpx.get(f"{self.base_url}/health", timeout=1)
                    if resp.status_code == 200:
                        return
                except (httpx.ConnectError, httpx.ReadTimeout):
                    pass
                time.sleep(0.2)
            raise TimeoutError(f"Server did not start within {timeout}s")

        def close(self):
            if self._client:
                self._client.close()

        def render(self):
            pass

else:
    class SlackToolEnv:
        """Stub when gymnasium is not installed."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "gymnasium is required for SlackToolEnv. "
                "Install with: pip install gymnasium"
            )
