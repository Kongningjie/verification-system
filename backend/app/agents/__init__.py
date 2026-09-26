"""OpenAI Agents SDK 适配层；后续阶段实现。"""

from app.agents.checklist import ChecklistGenerator, FakeChecklistGenerator, RealChecklistGenerator

__all__ = ["ChecklistGenerator", "FakeChecklistGenerator", "RealChecklistGenerator"]
