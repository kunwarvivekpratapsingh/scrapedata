import json
from crewai import Agent, Task, Crew

# ------------------------ #
# Step 1: Schema Extractor
# ------------------------ #
def extract_schema(data, prefix=""):
    schema = {}

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            schema.update(extract_schema(value, full_key))

    elif isinstance(data, list):
        for i, item in enumerate(data[:3]):  # Only sample a few list items
            schema.update(extract_schema(item, prefix + "[]"))
        if not data:
            schema[prefix + "[]"] = "empty_list"

    else:
        schema[prefix] = type(data).__name__

    return schema

# ------------------------ #
# Step 2: Robust Parser
# ------------------------ #
def parse_any_json(file_path):
    with open(file_path, 'r') as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        entries = list(raw.values())
        if all(isinstance(v, dict) for v in entries):
            sample_entries = entries[:3]
        else:
            sample_entries = [{k: v} for k, v in list(raw.items())[:3]]
    elif isinstance(raw, list):
        sample_entries = raw[:3]
    else:
        raise ValueError("Unsupported top-level JSON structure")

    schema = extract_schema(raw)
    return schema, sample_entries

# ------------------------ #
# Step 3: CrewAI Agent
# ------------------------ #
json_parser_agent = Agent(
    role="Recursive JSON Parser",
    goal="Parse and summarize the structure of a complex and deeply nested JSON file",
    backstory="You are a schema analyst who extracts insights from any JSON structure, no matter how irregular.",
    allow_llm=True,
    verbose=True
)

def create_flexible_schema_task(agent, schema: dict, sample_entries: list) -> Task:
    return Task(
        description=(
            f"You are analyzing a JSON structure with complex nesting. Your goals are:\n"
            f"- Summarize the schema using the provided key paths.\n"
            f"- Detect any nested arrays or objects.\n"
            f"- Point out if keys are missing or inconsistent.\n"
            f"- Recommend how to normalize or flatten the data for further use.\n\n"
            f"**Schema Summary:**\n{json.dumps(schema, indent=2)}\n\n"
            f"**Sample Entries:**\n{json.dumps(sample_entries, indent=2)}"
        ),
        expected_output="A structured markdown-friendly summary of the schema, its shape, and normalization recommendations.",
        agent=agent
    )

# ------------------------ #
# Step 4: Execution Logic
# ------------------------ #
def run_generic_json_parser(file_path: str):
    schema, sample_data = parse_any_json(file_path)
    task = create_flexible_schema_task(json_parser_agent, schema, sample_data)
    crew = Crew(tasks=[task], agents=[json_parser_agent], verbose=True)
    return crew.run()

# ------------------------ #
# Entry Point
# ------------------------ #
if __name__ == "__main__":
    file_path = "your_file.json"  # 🔁 Replace this with your actual JSON file path
    summary = run_generic_json_parser(file_path)
    print("\n===== JSON Structure Summary =====\n")
    print(summary)
