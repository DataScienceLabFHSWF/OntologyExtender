# Local LLaMA <-> Official Miro MCP Workspace

This folder gives you the full chain:

Miro Board <-> Official Miro MCP Server <-> MCP Client Bridge <-> Local LLaMA

## What is included

- `client_bridge.py`: MCP client that lets an OpenAI-compatible local model call the hosted Miro MCP tools
- `.env.example`: environment variables for Miro + local model
- `run_demo.sh`: one-command demo runner
- `requirements.txt`: Python dependencies

## Current capabilities

- Official hosted Miro MCP only (`https://mcp.miro.com/`)
- OAuth-based MCP authentication with local token cache (`.miro_oauth_tokens.json`)
- Default board/frame inference from `.env` when prompts do not include a Miro URL
- Deterministic diagram fallback for robust generation in target frame
- Ontology schema mode that generates labeled `entity_relationship` diagrams with semantic relation names
- Example ontology relation labels include `hasTopping`, `hasSauce`, `subClassOf`, and `goesOnTopOf`.

## 1) Setup

```bash
cd miro_mcp
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` and set:

- `MIRO_DEFAULT_BOARD_ID` or `MIRO_DEFAULT_BOARD_URL`
- `MIRO_DEFAULT_FRAME_URL` if you want frame-targeted prompts to work without pasting a Miro URL each time
- `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_MODEL`
- `MIRO_SKILL_CONTEXT_FILE` (optional, defaults to `SKILL.md`)

## Official Miro MCP

This workspace now targets the full official hosted Miro MCP server only.

Set in `.env`:

- `MIRO_MCP_URL=https://mcp.miro.com/`
- `MIRO_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/callback`
- `MIRO_DEFAULT_BOARD_ID=<board-id>` or `MIRO_DEFAULT_BOARD_URL=<full-board-url>`
- `MIRO_DEFAULT_FRAME_URL=<full-url-with-moveToWidget-or-focusWidget>`

Optional if you want to use your own Miro OAuth app:

- `MIRO_OAUTH_CLIENT_ID`
- `MIRO_OAUTH_CLIENT_SECRET`

When official mode is enabled, the bridge uses MCP Streamable HTTP transport and starts a browser-based OAuth flow if needed.

When a prompt does not include a Miro URL, the bridge falls back to the default board and frame values from `.env`.
If a prompt includes a board URL but no frame URL, the configured default frame is reused only when it belongs to the same default board.

Important:

- The redirect URI must be registered in your Miro app if you use your own app credentials.
- The official MCP connection uses OAuth via `.miro_oauth_tokens.json`; it does not use a REST bearer token from `.env`.

For Ollama, typical values are:

- `LOCAL_LLM_BASE_URL=http://localhost:11434/v1`
- `LOCAL_LLM_MODEL=llama3.1:8b`

## 2) Run the full chain

```bash
./run_demo.sh "Summarize this board and propose next steps"
```

Or run directly:

```bash
python client_bridge.py --prompt "List the most relevant board items"
```

Ontology schema example:

```bash
./run_demo.sh "Create a basic ontology of pizza and make a Miro diagram of the schema in the default frame. Include classes Pizza, Topping, Cheese, Sauce, Crust and semantic object properties."
```

Generic domain example:

```bash
./run_demo.sh "Create an ontology for university domain and make a schema diagram in the default frame."
```

## Known limitations

- Generic ontology prompts currently use a template-driven schema when class lists are vague.
- Prompts like "classes such as A, B, C" are not yet fully parsed into custom nodes/edges for all domains.
- The pizza ontology path is currently the most semantically rich built-in ontology preset.

## Notes

- The bridge uses OpenAI tool-calling format with your local model endpoint.
- The bridge connects directly to the hosted Miro MCP server and uses OAuth for MCP access.
- The bridge can inject skill guidance from `SKILL.md` to improve diagram execution consistency.
- If your local model does not reliably support tool-calling, switch to a tool-capable local model variant.
