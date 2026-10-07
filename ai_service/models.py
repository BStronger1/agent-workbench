from typing import Literal
from pydantic import BaseModel, Field, SecretStr, model_validator


class Step(BaseModel):
    action: Literal["check", "fill", "click", "assert_text", "assert_changed"]
    target: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    value: str = Field(default="", max_length=200)


class Contract(BaseModel):
    requiredTexts: list[str] = Field(default_factory=list, max_length=8)
    checkInteraction: bool = True
    steps: list[Step] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def executable(self):
        if any(not t.strip() or len(t) > 100 for t in self.requiredTexts):
            raise ValueError("Invalid required text")
        if self.steps:
            actions = [s.action for s in self.steps]
            if self.checkInteraction and (
                "click" not in actions
                or not any(a.startswith("assert_") for a in actions)
            ):
                raise ValueError("Interaction needs a click and assertion")
            if not actions[-1].startswith("assert_"):
                raise ValueError("Last step must assert a result")
            if any(s.action == "assert_text" and not s.value for s in self.steps):
                raise ValueError("Text assertions cannot be empty")
        return self


class Plan(BaseModel):
    summary: str = Field(max_length=1500)
    steps: list[Step] = Field(default_factory=list, max_length=12)


class Code(BaseModel):
    html: str = Field(min_length=20, max_length=150000)


class Review(BaseModel):
    issues: list[str] = Field(default_factory=list, max_length=8)


class Credentials(BaseModel):
    baseUrl: str
    model: str = Field(min_length=1, max_length=150)
    apiKey: SecretStr


class Source(BaseModel):
    id: str
    title: str
    excerpt: str
    score: float = 0


class RunInput(BaseModel):
    owner: str = Field(pattern=r"^[a-f0-9]{64}$")
    projectId: str = Field(pattern=r"^[a-f0-9-]{36}$")
    runId: str = Field(pattern=r"^[a-f0-9-]{36}$")
    prompt: str = Field(min_length=1, max_length=2000)
    workflow: Literal["graph_single", "graph_multi"]
    contract: Contract
    sources: list[Source] = Field(default_factory=list, max_length=8)
    maxRepairs: int = Field(default=1, ge=0, le=3)
    tokenBudget: int = Field(default=50000, ge=1000, le=50000)
    pauseAfterPlan: bool = False
    resume: bool = False
    credentials: Credentials


class KnowledgeInput(BaseModel):
    owner: str = Field(pattern=r"^[a-f0-9]{64}$")
    projectId: str = Field(pattern=r"^[a-f0-9-]{36}$")
    query: str = Field(min_length=1, max_length=1000)
    memories: list[dict] = Field(default_factory=list, max_length=200)
    documents: list[dict] = Field(default_factory=list, max_length=20)
    answer: bool = False
    credentials: Credentials | None = None


class Answer(BaseModel):
    answer: str = Field(max_length=4000)
    citations: list[str] = Field(default_factory=list, max_length=8)
