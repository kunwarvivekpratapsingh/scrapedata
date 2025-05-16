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

# dummy_memory_store.py

class DummySemanticStore:
    def retrieve(self, session_id, query, top_k=5):
        return [
            "User previously asked about sales by category.",
            "A chart was generated showing revenue trends.",
        ]

    def save(self, session_id, user_id, message):
        print(f"[DummySemanticStore] Saved semantic: ({session_id}, {message})")


class DummyEpisodicStore:
    def get_last_n(self, session_id, role=None, limit=5):
        return [
            {"role": "user", "message": "Show revenue breakdown by region."},
            {"role": "metaagent", "message": "Routing to bigdata agent."},
        ]

    def save_event(self, session_id, role, message):
        print(f"[DummyEpisodicStore] Saved episode: ({session_id}, {role}, {message})")

 def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.semantic_store = DummySemanticStore()
        self.episodic_store = DummyEpisodicStore()

"""
You are a supervisor tasked with routing a conversation to correct assistant: visualizer, retriever, coder, bigdata.       
Think carefully to whom pass the question. Take into consideration whole context.

Formulate task for each assistant taking into account if this is new request or additional information to previous question.
Do not skip any information, do not change the meaning of words.

Use QUESTION route to ask human a question. Do it always when you got response from ask_human tool.
Do not use QUESTION route to ask human for missing results from assistants.

Route to FINISH when you can answer the question based on results from assistants. Answer needs to be HTML compilant.

If assistant was not able to acomplish task and you cannot proceed further - answer with actual status.
You cannot except from Human that he will provide an answer to task assigned to assistant.

Responsibilities of assistants:
* retriever - his goal is to gather information which datasets should be used to get data and their schema
* coder - based on information from retriever he generates the code to be executed
* bigdata - an assistant responsible for executing code from coder and saving results to directory
* visualizer - responsible for presenting data (generate plot, table, save to csv) based on results from bigdata assistant

You cannot route to the same assistant twice in a row without human interaction between them.

Results from assistants that you can use to provide final answer:
* retriever
{datasets}

* bigdata output path: {result_output_path}

---

Below is memory from previous turns to help you decide:

--- SEMANTIC MEMORY ---
{{retrieved_memory}}

--- EPISODIC MEMORY ---
{{episodic_trace}}
"""
def __call__(self, state) -> Command:
    session_id = state["session_id"]
    user_id = state.get("user_id", "anonymous")
    question = state["user_question"]

    # 🧠 Retrieve semantic + episodic memory (from dummy or real store)
    sem_mem = self.semantic_store.retrieve(session_id, question)
    epi_mem = self.episodic_store.get_last_n(session_id)

    semantic_block = "\n".join(sem_mem) if sem_mem else "None"
    episodic_trace = "\n".join(f"{e['role']}: {e['message']}" for e in epi_mem) if epi_mem else "None"

    # ✅ Store into state for downstream agents
    state["retrieved_memory"] = sem_mem
    state["episodic_trace"] = episodic_trace

    # ✅ Build final system prompt using your class docstring
    memory_prompt = self.__class__.__doc__ \
        .replace("{{retrieved_memory}}", semantic_block) \
        .replace("{{episodic_trace}}", episodic_trace)

    # ✅ Inject system prompt into message stream
    state["messages"] = [{"role": "system", "content": memory_prompt}]

    # 🧠 Continue with your original behavior (routes & LLM call)
    response = super().__call__(state)
    goto = response.next

    # 🧠 Save current user question to both memories
    self.semantic_store.save(session_id, user_id, question)
    self.episodic_store.save_event(session_id, "user", question)

    # 🧠 Save LLM result to episodic memory
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
-- Create the eda_memory table
CREATE TABLE eda_memory (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    message TEXT NOT NULL,
    embedding VECTOR(1536),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Optional: Create an index on the vector column for fast similarity search
CREATE INDEX idx_eda_memory_embedding ON eda_memory USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Optional: Index to query by session quickly
CREATE INDEX idx_eda_memory_session_id ON eda_memory (session_id);


# eda_memory_store.py
from sqlalchemy import create_engine, Column, String, Integer, Text, TIMESTAMP
from sqlalchemy.orm import declarative_base, sessionmaker
from pgvector.sqlalchemy import Vector
from datetime import datetime
from langchain.embeddings import OpenAIEmbeddings

Base = declarative_base()

class EDAMemory(Base):
    __tablename__ = "eda_memory"

    id = Column(Integer, primary_key=True)
    session_id = Column(String)
    user_id = Column(String)
    message = Column(Text)
    embedding = Column(Vector(1536))
    timestamp = Column(TIMESTAMP, default=datetime.utcnow)

class EDAMemoryStore:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.embedder = OpenAIEmbeddings()

    def save(self, session_id, user_id, message):
        embedding = self.embedder.embed_query(message)
        with self.Session() as session:
            entry = EDAMemory(session_id=session_id, user_id=user_id, message=message, embedding=embedding)
            session.add(entry)
            session.commit()

    def retrieve(self, session_id, message, top_k=5, min_score=0.75):
        query_embedding = self.embedder.embed_query(message)
        with self.engine.connect() as conn:
            result = conn.execute(
                f"""
                SELECT message, embedding <-> :query AS score
                FROM eda_memory
                WHERE session_id = :sid
                ORDER BY score ASC
                LIMIT :limit
                """,
                {"query": query_embedding, "sid": session_id, "limit": top_k}
            )
            results = [row[0] for row in result.fetchall() if row[1] <= (1 - min_score)]
            return results
POSTGRES_URL=postgresql+psycopg2://eda_user:your_password@<your_host_or_ip>:5432/eda_memory_db


# test_connection.py

import os
from sqlalchemy import create_engine

# Set this only for quick testing
os.environ["POSTGRES_URL"] = "postgresql+psycopg2://eda_user:your_password@your_host:5432/eda_memory_db"

db_url = os.getenv("POSTGRES_URL")
engine = create_engine(db_url)

try:
    with engine.connect() as conn:
        result = conn.execute("SELECT * FROM eda_memory LIMIT 1;")
        print("✅ Connected! Sample data:", result.fetchall())
except Exception as e:
    print("❌ Connection failed:", e)



def retrieve(self, session_id: str, query: str, top_k: int = 5, min_score: float = 0.75):
        query_embedding = self.embedder.embed_query(query)

        # ✅ Convert Python list to pgvector-compatible string
        formatted_vector = "[" + ",".join(map(str, query_embedding)) + "]"

        with self.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT message, embedding <-> :query_embedding AS score
                    FROM eda_memory
                    WHERE session_id = :session_id
                    ORDER BY score ASC
                    LIMIT :limit
                """),
                {
                    "query_embedding": formatted_vector,
                    "session_id": session_id,
                    "limit": top_k
                }
            )
            return [
                row[0]
                for row in result.fetchall()
                if row[1] is not None and row[1] <= (1 - min_score)
            ]
