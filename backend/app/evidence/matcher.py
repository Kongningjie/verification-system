import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.models.document import BlockType, FileCategory
from app.models.task import VerificationTask
from app.schemas.checklist import SourceCategory
from app.schemas.execution import EvidenceCandidate, EvidenceRole


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return re.sub(r"\s+", " ", text).strip()


def search_terms(text: str) -> list[str]:
    normalized = normalize_text(text)
    english = re.findall(r"[a-z0-9][a-z0-9_.-]*", normalized)
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", normalized)
    ngrams = [chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))]
    if len(chinese) == 1:
        ngrams.append(chinese)
    return english + ngrams


def lexical_score(query: str, content: str, heading_path: list[str] | None = None) -> float:
    query_tokens = search_terms(query)
    if not query_tokens:
        return 0.0
    content_tokens = search_terms(content)
    counts = Counter(content_tokens)
    length = max(len(content_tokens), 1)
    score = sum((counts[token] / length) * (1 + math.log1p(len(token))) for token in query_tokens)
    normalized_query = normalize_text(query)
    normalized_content = normalize_text(content)
    if normalized_query and normalized_query in normalized_content:
        score += 3.0
    heading = normalize_text(" ".join(heading_path or []))
    score += sum(0.35 for token in set(query_tokens) if token in search_terms(heading))
    return round(score, 6)


def stable_evidence_id(check_item_id: str, origin: str) -> str:
    digest = hashlib.sha256(f"{check_item_id}|{origin}".encode()).hexdigest()[:32]
    return f"ev_{digest}"


@dataclass(frozen=True)
class MatchRequest:
    check_item_id: str
    requirement: str
    target_hint: str
    required_sources: list[SourceCategory]
    heading_path: list[str] | None = None


class EvidenceMatcher:
    def __init__(self, max_candidates_per_source: int = 8) -> None:
        self.max_candidates_per_source = max_candidates_per_source

    def match(self, task: VerificationTask, request: MatchRequest) -> list[EvidenceCandidate]:
        query = " ".join(
            [request.requirement, request.target_hint, *(request.heading_path or [])]
        ).strip()
        candidates: list[EvidenceCandidate] = []
        for task_file in task.files:
            if task_file.category == FileCategory.MANUAL_DOCX:
                candidates.extend(self._manual_candidates(request.check_item_id, task_file, query))
            elif task_file.category == FileCategory.EVIDENCE_PDF:
                candidates.extend(self._pdf_candidates(request.check_item_id, task_file, query))
            elif task_file.category == FileCategory.EVIDENCE_IMAGE:
                candidates.append(self._image_candidate(request.check_item_id, task_file, query))
        if task.project_metadata:
            project_file_id = next(
                (item.id for item in task.files if item.category == FileCategory.PROJECT_JSON),
                None,
            )
            candidates.extend(
                self._project_candidates(
                    request.check_item_id,
                    task.project_metadata.normalized_data,
                    query,
                    project_file_id,
                )
            )
        selected: list[EvidenceCandidate] = []
        for role in EvidenceRole:
            for category in SourceCategory:
                group = sorted(
                    (
                        item
                        for item in candidates
                        if item.role == role and item.source_category == category
                    ),
                    key=lambda item: (-item.score, item.evidence_id),
                )[: self.max_candidates_per_source]
                selected.extend(group)
        return selected

    def _manual_candidates(self, item_id: str, task_file, query: str) -> list[EvidenceCandidate]:
        result: list[EvidenceCandidate] = []
        for block in task_file.blocks:
            if not block.text.strip() and block.block_type != BlockType.IMAGE:
                continue
            heading = list(block.heading_path or [])
            structural_bonus = 0.25 if block.block_type == BlockType.TABLE_CELL else 0
            content = block.text.strip() or "[说明书图片]"
            result.append(
                EvidenceCandidate(
                    evidence_id=stable_evidence_id(
                        item_id, f"block:{task_file.id}:{block.block_id}"
                    ),
                    source_file_id=task_file.id,
                    role=EvidenceRole.TARGET,
                    source_category=SourceCategory.MANUAL,
                    content=content[:4000],
                    locator={
                        **(block.locator or {}),
                        "block_id": block.block_id,
                        "heading_path": heading,
                    },
                    score=lexical_score(query, content, heading) + structural_bonus,
                )
            )
        for asset in task_file.assets:
            nearby = [
                block
                for block in task_file.blocks
                if asset.asset_id in (block.related_asset_ids or [])
            ]
            context = " ".join(block.text for block in nearby if block.text).strip()
            result.append(
                EvidenceCandidate(
                    evidence_id=stable_evidence_id(
                        item_id, f"asset:{task_file.id}:{asset.asset_id}"
                    ),
                    source_file_id=task_file.id,
                    role=EvidenceRole.TARGET,
                    source_category=SourceCategory.MANUAL,
                    content=(context or "[说明书图片]")[:4000],
                    locator={
                        **(asset.locator or {}),
                        "asset_id": asset.asset_id,
                        "relationship_id": asset.relationship_id,
                    },
                    score=lexical_score(query, context) + 0.15,
                    asset_path=asset.storage_path,
                )
            )
        return result

    def _pdf_candidates(self, item_id: str, task_file, query: str) -> list[EvidenceCandidate]:
        return [
            EvidenceCandidate(
                evidence_id=stable_evidence_id(item_id, f"pdf:{task_file.id}:{block.block_id}"),
                source_file_id=task_file.id,
                role=EvidenceRole.SOURCE,
                source_category=SourceCategory.EVIDENCE_PDF,
                content=block.text[:4000],
                locator={**(block.locator or {}), "block_id": block.block_id},
                score=lexical_score(query, block.text, block.heading_path),
            )
            for block in task_file.blocks
            if block.text.strip()
        ]

    def _image_candidate(self, item_id: str, task_file, query: str) -> EvidenceCandidate:
        asset = task_file.assets[0] if task_file.assets else None
        path = asset.storage_path if asset else task_file.storage_path
        return EvidenceCandidate(
            evidence_id=stable_evidence_id(item_id, f"image:{task_file.id}"),
            source_file_id=task_file.id,
            role=EvidenceRole.SOURCE,
            source_category=SourceCategory.EVIDENCE_IMAGE,
            content=f"[依据图片] {task_file.original_name}",
            locator={"file_id": task_file.id, "original_name": task_file.original_name},
            score=lexical_score(query, task_file.original_name),
            asset_path=str(Path(path)),
        )

    def _project_candidates(
        self, item_id: str, data: dict, query: str, source_file_id: str | None
    ) -> list[EvidenceCandidate]:
        result: list[EvidenceCandidate] = []
        for section in ("project", "attributes"):
            values = data.get(section) or {}
            for key, value in values.items():
                if value is None or value == "" or value == []:
                    continue
                rendered = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
                content = f"{key}: {rendered}"
                result.append(
                    EvidenceCandidate(
                        evidence_id=stable_evidence_id(item_id, f"project:{section}:{key}"),
                        source_file_id=source_file_id,
                        role=EvidenceRole.SOURCE,
                        source_category=SourceCategory.PROJECT,
                        content=content,
                        locator={"section": section, "field": key},
                        score=lexical_score(query, content)
                        + (1.0 if normalize_text(key) in normalize_text(query) else 0),
                    )
                )
        return result
