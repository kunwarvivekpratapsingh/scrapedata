def __call__(self, state) -> Command:
    session_id = state["session_id"]
    user_id = state.get("user_id", "anonymous")
    question = state["user_question"]

    # Memory retrieval
    semantic_block = "\n".join(self.semantic_store.retrieve(session_id, question)) or "None"
    episodic_trace = "\n".join(f"{e['role']}: {e['message']}" for e in self.episodic_store.get_last_n(session_id)) or "None"

    # ✅ Store in state
    state["retrieved_memory"] = semantic_block.split("\n")
    state["episodic_trace"] = episodic_trace

    # Prompt memory injection
    self.llm.prefix_messages = [{
        "role": "system",
        "content": self.__class__.__doc__
            .replace("{{retrieved_memory}}", semantic_block)
            .replace("{{episodic_trace}}", episodic_trace)
    }]

    # Optional defaults for downstream
    state["datasets"] = state.get("datasets", "TODO")
    state["result_output_path"] = state.get("data", "TODO")

    # LLM call
    response = super().__call__(state)
    goto = response.next

    # Save episodic memory
    self.semantic_store.save(session_id, user_id, question)
    self.episodic_store.save_event(session_id, "user", question)

    if goto == "FINISH":
        self.episodic_store.save_event(session_id, "metaagent", response.answer)
        content = response.answer
    elif goto == "QUESTION":
        self.episodic_store.save_event(session_id, "metaagent", response.question)
        content = response.question
    else:
        self.episodic_store.save_event(session_id, "metaagent", response.task)
        content = response.task

    return Command(goto=goto, update={"messages": self._create_ai_message(content)})
