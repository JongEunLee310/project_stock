from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.knowledge.model import KnowledgeDocument
from app.domains.knowledge.schema import KnowledgeDocumentCreate
from app.domains.knowledge.types import KnowledgeKind


class KnowledgeDocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_external_id(
        self, kind: KnowledgeKind, external_id: str
    ) -> KnowledgeDocument | None:
        """종류와 외부 식별자로 수집한 문서를 조회한다."""
        return self.db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.kind == kind.value,
                KnowledgeDocument.external_id == external_id,
            )
        )

    def add(self, data: KnowledgeDocumentCreate) -> KnowledgeDocument:
        """문서를 저장하고 flush한다. commit은 호출자가 수행한다."""
        document = KnowledgeDocument(**data.model_dump())
        self.db.add(document)
        self.db.flush()
        return document

    def list_after_id(self, after_id: int, limit: int) -> list[KnowledgeDocument]:
        """인덱서가 읽을 문서를 id 오름차순으로 조회한다."""
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id > after_id)
            .order_by(KnowledgeDocument.id)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def list_by_asset(
        self, asset_id: int, kind: KnowledgeKind, limit: int
    ) -> list[KnowledgeDocument]:
        """종목과 종류가 일치하는 문서를 유효일 최신순으로 조회한다."""
        stmt = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.asset_id == asset_id,
                KnowledgeDocument.kind == kind.value,
            )
            .order_by(
                KnowledgeDocument.effective_date.desc().nullslast(),
                KnowledgeDocument.id.desc(),
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
