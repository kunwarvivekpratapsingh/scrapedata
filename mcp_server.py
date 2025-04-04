# mcp_server.py

from typing import Union, List, Dict, Any
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("SegmentRuleMCPServer", "Parses segment definitions and outputs human-readable rules as JSON.")

# Utility: Map operators to readable phrases
def format_operator(op: str) -> str:
    return {
        "==": "equals",
        "=": "is",
        ">": "greater than",
        "<": "less than",
        ">=": "at least",
        "<=": "at most",
        "!=": "not equal to"
    }.get(op, op)

# Utility: Humanize field names (e.g., "user_age" -> "User Age")
def humanize_field(field: str) -> str:
    return field.replace("_", " ").title()

# Leaf node condition
def format_condition(cond: Dict[str, Any]) -> Dict[str, Any]:
    field = humanize_field(cond["field"])
    op = format_operator(cond["operator"])
    val = cond["value"]
    return {
        "field": field,
        "condition": op,
        "value": val,
        "description": f"{field} {op} {val}"
    }

# Recursive function to parse all/any/not structures
def parse_conditions(cond_block: Union[Dict[str, Any], List]) -> Dict[str, Any]:
    if isinstance(cond_block, list):
        # fallback if list given directly
        return {
            "type": "all",
            "children": [parse_conditions(c) for c in cond_block]
        }

    if "all" in cond_block:
        return {
            "type": "all",
            "children": [parse_conditions(c) for c in cond_block["all"]]
        }
    elif "any" in cond_block:
        return {
            "type": "any",
            "children": [parse_conditions(c) for c in cond_block["any"]]
        }
    elif "not" in cond_block:
        return {
            "type": "not",
            "child": parse_conditions(cond_block["not"])
        }
    else:
        return format_condition(cond_block)

# Main processor
def generate_human_readable_json_nested(raw_segments: Dict[str, Any]) -> Dict[str, Any]:
    output = {"segments": []}

    for seg in raw_segments.get("segments", []):
        name = humanize_field(seg.get("name", "Unnamed Segment"))
        raw_conditions = seg.get("conditions", {})

        readable_rules = parse_conditions(raw_conditions)

        output["segments"].append({
            "segmentName": name,
            "rules": readable_rules
        })

    return output

# MCP Tool Endpoint
@mcp.tool()
def translate_segments(segment_json: dict) -> dict:
    """
    Converts ML-generated segment definition JSON into a human-readable nested JSON structure.
    Supports logical conditions: all (AND), any (OR), not (NOT).
    """
    return generate_human_readable_json_nested(segment_json)

# Run the MCP server
if __name__ == "__main__":
    mcp.run()
