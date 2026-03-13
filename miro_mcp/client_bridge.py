import argparse
import asyncio
import json
import os
import re
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken


load_dotenv()


def _get_official_mcp_url() -> str:
    return os.getenv("MIRO_MCP_URL", "https://mcp.miro.com/").strip()


def _build_openai_client() -> OpenAI:
    base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1").strip()
    api_key = os.getenv("LOCAL_LLM_API_KEY", "not-needed")
    return OpenAI(base_url=base_url, api_key=api_key)


def _tool_schema_from_mcp_tool(tool: Any) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


def _extract_text_from_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result

    content = getattr(result, "content", None)
    if not content:
        return str(result)

    out: list[str] = []
    for chunk in content:
        text_value = getattr(chunk, "text", None)
        if text_value is not None:
            out.append(text_value)
            continue

        if isinstance(chunk, dict) and "text" in chunk:
            out.append(str(chunk["text"]))
            continue

        out.append(str(chunk))

    return "\n".join(out)


def _extract_context_from_miro_url(url: str) -> tuple[str | None, str | None]:
    board_id: str | None = None
    frame_id: str | None = None

    board_match = re.search(r"/board/([^/]+)/", url)
    if board_match:
        board_id = board_match.group(1)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    frame_values = query.get("moveToWidget") or query.get("focusWidget")
    if frame_values and frame_values[0].strip():
        frame_id = frame_values[0].strip()

    return board_id, frame_id


def _get_default_miro_context() -> tuple[str | None, str | None]:
    board_id = os.getenv("MIRO_DEFAULT_BOARD_ID", "").strip() or None
    board_url = os.getenv("MIRO_DEFAULT_BOARD_URL", "").strip()
    frame_url = os.getenv("MIRO_DEFAULT_FRAME_URL", "").strip()

    board_from_board_url, _ = _extract_context_from_miro_url(board_url) if board_url else (None, None)
    board_from_frame_url, frame_id = _extract_context_from_miro_url(frame_url) if frame_url else (None, None)

    return board_id or board_from_board_url or board_from_frame_url, frame_id


def _extract_miro_context(text: str) -> tuple[str | None, str | None]:
    explicit_board_id: str | None = None
    explicit_frame_id: str | None = None

    for url in re.findall(r"https?://\S+", text):
        board_id, frame_id = _extract_context_from_miro_url(url)
        if board_id and explicit_board_id is None:
            explicit_board_id = board_id
        if frame_id and explicit_frame_id is None:
            explicit_frame_id = frame_id

    default_board_id, default_frame_id = _get_default_miro_context()

    board_id = explicit_board_id or default_board_id
    frame_id = explicit_frame_id
    if frame_id is None and (explicit_board_id is None or explicit_board_id == default_board_id):
        frame_id = default_frame_id

    return board_id, frame_id


def _infer_steps_from_prompt(prompt: str) -> list[str]:
    cleaned = prompt.replace("\n", " ").strip()
    step_count = 5
    count_match = re.search(r"\b(\d+)\s*[- ]?step", cleaned.lower())
    if count_match:
        step_count = max(2, min(int(count_match.group(1)), 8))

    if ":" in cleaned:
        tail = cleaned.split(":", 1)[1].strip()
    else:
        tail = cleaned

    candidates = [p.strip(" .") for p in re.split(r",|->|→", tail) if p.strip(" .")]
    if len(candidates) >= 2:
        return candidates[:step_count]

    defaults = [
        "Ingest source documents",
        "Extract entities and relations",
        "Build knowledge graph triples",
        "Validate against ontology",
        "Publish and review",
        "Refine ontology structure",
        "Run competency checks",
        "Publish final ontology",
    ]
    return defaults[:step_count]


def _build_flowchart_dsl(steps: list[str]) -> str:
    cleaned_steps = [step.strip() for step in steps if step.strip()]
    if not cleaned_steps:
        cleaned_steps = ["Start", "Finish"]
    elif len(cleaned_steps) == 1:
        cleaned_steps.append("Finish")

    lines = ["graphdir LR", "palette #fff6b6 #c6dcff #adf0c7", ""]

    last_index = len(cleaned_steps)
    for idx, label in enumerate(cleaned_steps, start=1):
        if idx == 1 or idx == last_index:
            shape = "flowchart-terminator"
            color_index = 2
        else:
            shape = "flowchart-process"
            color_index = 0
        lines.append(f"n{idx} {label} {shape} {color_index}")

    lines.append("")
    for idx in range(1, last_index):
        lines.append(f"c n{idx} - n{idx + 1}")

    return "\n".join(lines)


def _infer_ontology_subject(prompt: str) -> str:
    lowered = prompt.lower()
    if "pizza" in lowered:
        return "Pizza"
    match = re.search(r"ontology\s+(?:of|for)\s+([a-z0-9 -]+?)(?:\s+(?:and|with|in|on)\b|[.,]|$)", lowered)
    if match:
        return match.group(1).strip().title()
    return "Domain"


def _build_er_entity(
    node_id: str,
    label: str,
    attributes: list[tuple[str, str, str]],
    color: str = "#fff6b6",
) -> str:
    attr_lines = []
    for key, field, data_type in attributes:
        prefix = key if key else ""
        attr_lines.append(f"{prefix}\t{field}\t{data_type}")
    attr_block = "\n".join(attr_lines)
    return f'{node_id} "{label}" "{attr_block}" {color}'


def _build_pizza_ontology_dsl() -> str:
    lines = [
        "graphdir LR",
        "",
        _build_er_entity("n1", "Pizza", [("PK", "pizza_id", "string"), ("", "name", "string"), ("", "size", "string")]),
        _build_er_entity("n2", "Topping", [("PK", "topping_id", "string"), ("", "name", "string")]),
        _build_er_entity("n3", "Cheese", [("PK", "cheese_id", "string"), ("", "milk_type", "string")]),
        _build_er_entity("n4", "Sauce", [("PK", "sauce_id", "string"), ("", "base", "string")]),
        _build_er_entity("n5", "Crust", [("PK", "crust_id", "string"), ("", "style", "string"), ("", "thickness", "string")]),
        _build_er_entity("n6", "MeatTopping", [("PK", "meat_topping_id", "string"), ("", "protein", "string")]),
        _build_er_entity("n7", "VegetableTopping", [("PK", "vegetable_topping_id", "string"), ("", "plant_type", "string")]),
        "",
        'e1 "hasTopping" n1 one .. zero_or_many n2',
        'e2 "hasSauce" n1 one .. only_one n4',
        'e3 "hasCrust" n1 one .. only_one n5',
        'e4 "subClassOf" n3 one .. one n2',
        'e5 "subClassOf" n6 one .. one n2',
        'e6 "subClassOf" n7 one .. one n2',
        'e7 "goesOnTopOf" n3 zero_or_many .. one n5',
        'e8 "goesOnTopOf" n6 zero_or_many .. one n5',
        'e9 "goesOnTopOf" n7 zero_or_many .. one n5',
        'e10 "covers" n4 one .. one n5',
    ]
    return "\n".join(lines)


def _build_generic_ontology_dsl(subject: str) -> str:
    safe_subject = subject or "Domain"
    lines = [
        "graphdir LR",
        "",
        _build_er_entity("n1", safe_subject, [("PK", f"{safe_subject.lower()}_id", "string"), ("", "name", "string"), ("", "description", "string")]),
        _build_er_entity("n2", f"{safe_subject}Category", [("PK", "category_id", "string"), ("", "label", "string")]),
        _build_er_entity("n3", f"{safe_subject}Component", [("PK", "component_id", "string"), ("", "name", "string")]),
        _build_er_entity("n4", f"{safe_subject}Property", [("PK", "property_id", "string"), ("", "key", "string"), ("", "value_type", "string")]),
        _build_er_entity("n5", f"{safe_subject}Relation", [("PK", "relation_id", "string"), ("", "predicate", "string")]),
        "",
        f'e1 "hasCategory" n1 one .. zero_or_many n2',
        f'e2 "hasComponent" n1 one .. zero_or_many n3',
        f'e3 "hasProperty" n1 one .. zero_or_many n4',
        f'e4 "hasRelation" n1 one .. zero_or_many n5',
        f'e5 "classifies" n2 one .. zero_or_many n3',
    ]
    return "\n".join(lines)


def _build_ontology_schema_dsl(prompt: str) -> tuple[str, str, str]:
    subject = _infer_ontology_subject(prompt)
    if subject.lower() == "pizza":
        return "Pizza Ontology", "entity_relationship", _build_pizza_ontology_dsl()
    return f"{subject} Ontology", "entity_relationship", _build_generic_ontology_dsl(subject)


def _should_force_ontology_schema(prompt: str, frame_id: str | None) -> bool:
    lowered = prompt.lower()
    asks_schema = any(word in lowered for word in ("ontology", "schema", "class diagram", "uml"))
    asks_action = any(word in lowered for word in ("create", "make", "draw", "build", "generate"))
    return bool(frame_id) and asks_schema and asks_action


def _should_force_diagram(prompt: str, frame_id: str | None) -> bool:
    lowered = prompt.lower()
    asks_diagram = any(word in lowered for word in ("diagram", "flowchart", "chart", "schema"))
    asks_action = any(word in lowered for word in ("create", "make", "draw", "build", "generate"))
    return asks_diagram and asks_action and bool(frame_id)


def _should_list_tools(prompt: str) -> bool:
    lowered = prompt.lower()
    return "tool" in lowered and any(word in lowered for word in ("available", "what", "list", "show"))


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    parts = text.split("\n---\n", 1)
    if len(parts) == 2:
        return parts[1]
    return text


def _load_skill_context() -> str:
    path = os.getenv("MIRO_SKILL_CONTEXT_FILE", "SKILL.md").strip()
    if not path:
        return ""
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _strip_frontmatter(f.read()).strip()
    except OSError:
        return ""


class JsonTokenStorage:
    def __init__(
        self,
        file_path: str,
        fixed_client_info: OAuthClientInformationFull | None = None,
    ):
        self.file_path = Path(file_path)
        self.fixed_client_info = fixed_client_info

    def _read_data(self) -> dict[str, Any]:
        if not self.file_path.exists():
            return {}
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_data(self, data: dict[str, Any]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def get_tokens(self) -> OAuthToken | None:
        data = self._read_data()
        raw = data.get("tokens")
        if not raw:
            return None
        return OAuthToken.model_validate(raw)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read_data()
        data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self._write_data(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        data = self._read_data()
        raw = data.get("client_info")
        if not raw:
            return self.fixed_client_info
        return OAuthClientInformationFull.model_validate(raw)

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read_data()
        data["client_info"] = client_info.model_dump(mode="json", exclude_none=True)
        self._write_data(data)


async def _redirect_handler(url: str) -> None:
    print("Open this URL in your browser to authorize Miro MCP:")
    print(url)
    try:
        webbrowser.open(url)
    except Exception:
        pass


async def _callback_handler() -> tuple[str, str | None]:
    redirect_uri = os.getenv("MIRO_OAUTH_REDIRECT_URI", "http://127.0.0.1:8765/callback").strip()
    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    expected_path = parsed.path or "/callback"
    loop = asyncio.get_running_loop()
    result_future: asyncio.Future[tuple[str, str | None]] = loop.create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_data = await reader.read(65536)
            request_text = request_data.decode("utf-8", errors="ignore")
            first_line = request_text.splitlines()[0] if request_text else ""
            parts = first_line.split(" ")
            target = parts[1] if len(parts) >= 2 else "/"
            target_parsed = urlparse(target)

            if target_parsed.path != expected_path:
                body = b"Not found"
                writer.write(
                    b"HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
                return

            query = parse_qs(target_parsed.query)
            code = query.get("code", [""])[0]
            state = query.get("state", [None])[0]
            body = (
                b"Miro MCP authorization complete. You can return to the terminal and VS Code."
            )
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            await writer.drain()
            if not result_future.done():
                result_future.set_result((code, state))
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, host, port)
    print(f"Waiting for OAuth callback on {redirect_uri}")
    try:
        async with server:
            return await asyncio.wait_for(result_future, timeout=300)
    finally:
        server.close()
        await server.wait_closed()


def _build_oauth_provider(server_url: str) -> OAuthClientProvider:
    redirect_uri = os.getenv("MIRO_OAUTH_REDIRECT_URI", "http://127.0.0.1:8765/callback").strip()
    client_id = os.getenv("MIRO_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("MIRO_OAUTH_CLIENT_SECRET", "").strip()
    fixed_client_info: OAuthClientInformationFull | None = None
    token_auth_method = "none"

    if client_id and client_secret:
        token_auth_method = "client_secret_post"
        fixed_client_info = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=[redirect_uri],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="client_secret_post",
        )

    storage_path = os.getenv(
        "MIRO_OAUTH_STORAGE_FILE",
        ".miro_oauth_tokens.json",
    ).strip()
    storage = JsonTokenStorage(storage_path, fixed_client_info=fixed_client_info)

    client_metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method=token_auth_method,
        client_name="Local LLaMA Miro MCP Bridge",
    )

    provider = OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
    )

    return provider


def _build_remote_http_client(server_url: str) -> httpx.AsyncClient:
    headers = {"X-AI-Source": os.getenv("MIRO_X_AI_SOURCE", "local-llama-bridge")}
    auth = _build_oauth_provider(server_url)
    return create_mcp_http_client(headers=headers, auth=auth)


async def _run_with_session(
    session: ClientSession,
    prompt: str,
    inferred_board_id: str | None,
    inferred_frame_id: str | None,
    skill_context: str,
    max_rounds: int,
) -> str:
    await session.initialize()
    tools_result = await session.list_tools()
    mcp_tools = getattr(tools_result, "tools", [])
    llm_tools = [_tool_schema_from_mcp_tool(t) for t in mcp_tools]
    available_tool_names = {t.name for t in mcp_tools}

    if _should_list_tools(prompt):
        tool_lines = [f"- {tool.name}: {tool.description or 'No description'}" for tool in mcp_tools]
        return "Available MCP tools:\n" + "\n".join(tool_lines)

    if (
        _should_force_ontology_schema(prompt, inferred_frame_id)
        and {"diagram_get_dsl", "diagram_create"}.issubset(available_tool_names)
        and inferred_board_id
    ):
        title, diagram_type, dsl = _build_ontology_schema_dsl(prompt)
        await session.call_tool(
            "diagram_get_dsl",
            {"board_id": inferred_board_id, "diagram_type": diagram_type},
        )
        result = await session.call_tool(
            "diagram_create",
            {
                "board_id": inferred_board_id,
                "diagram_dsl": dsl,
                "diagram_type": diagram_type,
                "title": title,
                "parent_id": inferred_frame_id,
            },
        )
        return (
            "Created official Miro MCP ontology schema in target frame via deterministic fallback.\n"
            + _extract_text_from_tool_result(result)
        )

    if (
        _should_force_diagram(prompt, inferred_frame_id)
        and {"diagram_get_dsl", "diagram_create"}.issubset(available_tool_names)
        and inferred_board_id
    ):
        steps = _infer_steps_from_prompt(prompt)
        await session.call_tool(
            "diagram_get_dsl",
            {"board_id": inferred_board_id, "diagram_type": "flowchart"},
        )
        dsl = _build_flowchart_dsl(steps)
        result = await session.call_tool(
            "diagram_create",
            {
                "board_id": inferred_board_id,
                "diagram_dsl": dsl,
                "diagram_type": "flowchart",
                "title": steps[0] if steps else "Generated Flowchart",
                "parent_id": inferred_frame_id,
            },
        )
        return (
            "Created official Miro MCP diagram in target frame via deterministic fallback.\n"
            + _extract_text_from_tool_result(result)
        )

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a pragmatic assistant using Miro MCP tools. "
                "Use tools when needed, then return a concise final answer. "
                "Do not invent board IDs. If the user does not provide a concrete "
                "board ID or URL, omit board_id so the MCP server default is used. "
                "When the user asks for an ontology or schema with semantic object properties, call "
                "diagram_get_dsl with entity_relationship and then diagram_create so relations can be labeled. "
                "When the user asks to create or draw a diagram/flowchart, call "
                "diagram_get_dsl first and then diagram_create. If a frame id is provided, "
                "pass it as parent_id to diagram_create."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    if skill_context:
        messages.append(
            {
                "role": "system",
                "content": "Miro execution context and best practices:\n" + skill_context,
            }
        )

    if inferred_board_id or inferred_frame_id:
        guidance = []
        if inferred_board_id:
            guidance.append(f"board_id={inferred_board_id}")
        if inferred_frame_id:
            guidance.append(f"frame_id={inferred_frame_id}")
        messages.append(
            {
                "role": "system",
                "content": (
                    "Context extracted from user Miro URL: "
                    + ", ".join(guidance)
                    + ". Use these exact IDs when calling tools."
                ),
            }
        )

    client = _build_openai_client()
    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=os.getenv("LOCAL_LLM_MODEL", "llama3.1:8b").strip(),
            messages=messages,
            tools=llm_tools,
            tool_choice="auto",
            temperature=0.2,
        )

        assistant_message = response.choices[0].message
        tool_calls = assistant_message.tool_calls or []

        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
                if tool_calls
                else None,
            }
        )

        if not tool_calls:
            return assistant_message.content or ""

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            raw_args = tool_call.function.arguments or "{}"
            try:
                parsed_args = json.loads(raw_args)
            except json.JSONDecodeError:
                parsed_args = {}

            tool_result = await session.call_tool(tool_name, parsed_args)
            tool_text = _extract_text_from_tool_result(tool_result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_text,
                }
            )

    return "Stopped after max_rounds without a final answer."


async def run(prompt: str, max_rounds: int = 8) -> str:
    inferred_board_id, inferred_frame_id = _extract_miro_context(prompt)
    skill_context = _load_skill_context()
    server_url = _get_official_mcp_url()
    async with _build_remote_http_client(server_url) as http_client:
        async with streamable_http_client(server_url, http_client=http_client) as transport:
            reader, writer, _get_session_id = transport
            async with ClientSession(reader, writer) as session:
                return await _run_with_session(
                    session,
                    prompt,
                    inferred_board_id,
                    inferred_frame_id,
                    skill_context,
                    max_rounds,
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bridge a local OpenAI-compatible LLaMA model to the official Miro MCP server"
    )
    parser.add_argument("--prompt", required=True, help="User prompt for the assistant")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=8,
        help="Maximum model/tool interaction rounds",
    )
    args = parser.parse_args()

    final_text = asyncio.run(run(args.prompt, max_rounds=args.max_rounds))
    print(final_text)


if __name__ == "__main__":
    main()
