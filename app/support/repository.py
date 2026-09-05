from sqlalchemy import select
from sqlalchemy.orm import Session

from app.support.models import SupportInteraction, SupportKnowledge


class SupportKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> SupportKnowledge | None:
        statement = select(SupportKnowledge).where(SupportKnowledge.id == 1)
        return self.session.scalar(statement)

    def add(self, knowledge: SupportKnowledge) -> None:
        self.session.add(knowledge)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def refresh(self, knowledge: SupportKnowledge) -> None:
        self.session.refresh(knowledge)


class SupportInteractionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_external_update(
        self,
        platform: str,
        external_update_id: str,
    ) -> SupportInteraction | None:
        statement = select(SupportInteraction).where(
            SupportInteraction.platform == platform,
            SupportInteraction.external_update_id == external_update_id,
        )
        return self.session.scalar(statement)

    def add(self, interaction: SupportInteraction) -> None:
        self.session.add(interaction)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
