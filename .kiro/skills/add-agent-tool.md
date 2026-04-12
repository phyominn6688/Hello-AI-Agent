# Skill: Add a New Agent Tool

Use this skill when adding a new MCP-style tool to the travel agent's tool system.

## Steps

1. **Create the module** in `travel-agent/backend/app/agent/mcp/<tool_name>.py`

   Each module must expose two functions:
   ```python
   def get_tools() -> list:
       # Returns a list of Anthropic tool definitions (JSON schema)
       ...

   async def execute_tool(name: str, input: dict):
       # Calls the external API and returns the result
       ...
   ```

2. **Register the tool** in `travel-agent/backend/app/agent/travel_agent.py`:
   - Import the new module
   - Add `get_tools()` output to `PLANNING_TOOLS` and/or `GUIDE_TOOLS` as appropriate
   - Add an entry to `TOOL_DISPATCH` mapping the tool name to `execute_tool`

3. **Handle missing API keys gracefully** — MCP wrappers should return mock/stub data when the external API key is not configured, so local dev works without all credentials.

## Reference

Existing tools to use as examples:
- `backend/app/agent/mcp/weather.py` — simple external API wrapper
- `backend/app/agent/mcp/amadeus.py` — flight search
- `backend/app/agent/mcp/opentable.py` — restaurant reservations
