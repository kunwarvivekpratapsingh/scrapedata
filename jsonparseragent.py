from crewai import Task, Agent, Crew
import json

# ------------------------ #
# Agent Definition
# ------------------------ #
json_parser_agent = Agent(
    role="JSON Schema Summarizer",
    goal="Analyze and summarize any JSON structure including nested fields",
    backstory=(
        "You are a JSON analysis expert skilled at identifying structure, keys, nesting, and abnormalities in large or complex JSON datasets."
    ),
    allow_llm=True,
    verbose=True
)

# ------------------------ #
# Task Builder
# ------------------------ #
def build_json_parser_task(agent, records, unique_keys, has_nested, sample_entries, structural_issues):
    summary_input = (
        f"1. Total records: {records}\n"
        f"2. Unique keys: {unique_keys}\n"
        f"3. Any nested dictionaries or arrays: {has_nested}\n"
        f"4. Sample entries: {json.dumps(sample_entries, indent=2)}\n"
        f"5. Structural issues (if any): {structural_issues}\n"
        f"6. Final Python data structure: List[Dict[str, Any]]\n"
    )

    return Task(
        description=(
            "You are given the result of parsing a JSON file. Based on this input, generate a markdown report "
            "that summarizes the JSON structure, key fields, sample data, and any irregularities. "
            "Offer insights that can help further visualization or analysis."
        ),
        expected_output="A markdown summary of the parsed JSON structure, highlighting keys, structure, and insights.",
        agent=agent,
        input=summary_input
    )

# ------------------------ #
# Utility Functions
# ------------------------ #
def extract_schema(data, prefix=""):
    schema = {}
    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            schema.update(extract_schema(value, full_key))
    elif isinstance(data, list):
        for i, item in enumerate(data[:3]):
            schema.update(extract_schema(item, prefix + "[]"))
        if not data:
            schema[prefix + "[]"] = "empty_list"
    else:
        schema[prefix] = type(data).__name__
    return schema

def parse_json_and_run(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)

    # Handle root-level dict or list
    if isinstance(data, dict):
        values = list(data.values())
        records = len(values)
        sample_entries = values[:3]
    elif isinstance(data, list):
        records = len(data)
        sample_entries = data[:3]
    else:
        raise ValueError("Unsupported JSON structure. Root must be list or dict.")

    # Extract schema
    schema = extract_schema(data)
    unique_keys = list(set(schema.keys()))
    has_nested = any("[]" in key or "." in key for key in unique_keys)
    structural_issues = "Some records have missing or inconsistent keys."  # Optional enhancement

    task = build_json_parser_task(
        agent=json_parser_agent,
        records=records,
        unique_keys=unique_keys,
        has_nested=has_nested,
        sample_entries=sample_entries,
        structural_issues=structural_issues
    )

    crew = Crew(agents=[json_parser_agent], tasks=[task], verbose=True)
    result = crew.kickoff()
    print("\n\n========== JSON Summary Report ==========")
    print(result)

# ------------------------ #
# Main Entry Point
# ------------------------ #
if __name__ == "__main__":
    parse_json_and_run("your_file.json")  # Replace with your actual file path
