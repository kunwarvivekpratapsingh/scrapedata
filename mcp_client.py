# mcp_client.py

import httpx
import uuid
import json

MCP_ENDPOINT = "http://localhost:3333/rpc"  # FastMCP default dev URL

# Sample input with nested AND/OR/NOT logic
sample_segment_payload = {
    "segments": [
        {
            "name": "PowerUsers",
            "conditions": {
                "all": [
                    {"field": "login_count", "operator": ">", "value": 10},
                    {
                        "any": [
                            {"field": "subscription_level", "operator": "==", "value": "premium"},
                            {"field": "spend", "operator": ">", "value": 100}
                        ]
                    },
                    {
                        "not": {
                            "field": "is_banned", "operator": "==", "value": True
                        }
                    }
                ]
            }
        }
    ]
}

def call_translate_segments():
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "translate_segments",
        "params": {
            "segment_json": sample_segment_payload
        }
    }

    try:
        response = httpx.post(MCP_ENDPOINT, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        if "result" in result:
            print("\n✅ Human-readable JSON Response:")
            print(json.dumps(result["result"], indent=2))
        else:
            print("\n❌ Error in MCP response:", result.get("error", {}))

    except Exception as e:
        print(f"❌ MCP call failed: {e}")

if __name__ == "__main__":
    call_translate_segments()
