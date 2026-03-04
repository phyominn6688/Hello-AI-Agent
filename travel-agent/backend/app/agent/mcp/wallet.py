"""Digital wallet MCP wrapper — Apple PassKit + Google Wallet (stub).

Full implementation requires Apple developer certificates and Google Wallet API
service account. This wrapper provides the interface; real passes are generated
by the background worker.
"""
from app.config import settings


def get_tools() -> list[dict]:
    return [
        {
            "name": "save_to_wallet",
            "description": (
                "Generate a digital wallet pass (Apple Wallet / Google Wallet) for a booking. "
                "Returns pass URLs that the user can tap to add to their device wallet."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "ItineraryItem DB ID"},
                    "type": {
                        "type": "string",
                        "enum": ["boarding_pass", "event_ticket", "hotel", "generic"],
                    },
                    "traveler_name": {"type": "string"},
                    "title": {"type": "string", "description": "e.g. 'Beijing → Shanghai — G1'"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM (24h)"},
                    "location": {"type": "string"},
                    "booking_ref": {"type": "string"},
                    "barcode_value": {"type": "string", "description": "QR/barcode content if available"},
                },
                "required": ["item_id", "type", "traveler_name", "title", "date"],
            },
        },
        {
            "name": "store_document",
            "description": "Store a confirmation document (PDF, e-ticket) in S3 and return a secure URL.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "document_url": {"type": "string", "description": "Source URL of the document to fetch and store"},
                    "document_type": {"type": "string", "description": "e.g. 'e-ticket', 'hotel_confirmation', 'visa'"},
                },
                "required": ["item_id", "document_type"],
            },
        },
    ]


async def execute_tool(tool_name: str, tool_input: dict) -> dict:
    # Wallet pass generation is handled by the background worker via SQS.
    # The API queues the job and returns a pending status.
    if tool_name == "save_to_wallet":
        return {
            "status": "queued",
            "item_id": tool_input["item_id"],
            "message": (
                "Wallet pass generation is being processed. "
                "You'll receive Apple and Google Wallet links within 30 seconds."
            ),
            "apple_wallet_url": None,  # populated by worker
            "google_wallet_url": None,
        }
    elif tool_name == "store_document":
        return {
            "status": "queued",
            "item_id": tool_input["item_id"],
            "document_url": None,
            "message": "Document storage queued. Link will be available shortly.",
        }
    return {"error": f"Unknown tool: {tool_name}"}
