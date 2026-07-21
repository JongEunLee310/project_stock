from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.decision_logs.model import DecisionLog, DecisionReview
from app.domains.decision_logs.repository import (
    DecisionLogRepository,
    DecisionReviewRepository,
)
from app.domains.decision_logs.schema import (
    DecisionActivateRequest,
    DecisionEvidenceInput,
    DecisionEvidenceResponse,
    DecisionLogCreate,
    DecisionLogDetailResponse,
    DecisionLogListItem,
    DecisionOverviewResponse,
    DecisionLogResponse,
    DecisionLogUpdate,
    DecisionReviewCreate,
    DecisionReviewResponse,
    DecisionReviewTriggerResponse,
    DecisionRiskResponse,
    DecisionSnapshotResponse,
    DecisionTarget,
    DecisionTypeDistributionItem,
)
from app.domains.decision_logs.types import (
    ConfidenceLevel,
    DecisionStatus,
    DecisionType,
    EvidenceRelationship,
    OutcomeStatus,
    TargetType,
    ThesisResult,
)

SUMMARY_MAX_LENGTH = 200


class DecisionLogService:
    def __init__(self, db: Session) -> None:
        self.repo = DecisionLogRepository(db)
        self.review_repo = DecisionReviewRepository(db)

    def create_decision(
        self,
        user_id: int,
        data: DecisionLogCreate,
    ) -> DecisionLogResponse:
        evidence = [
            *data.evidence,
            *self._text_evidence(
                data.supporting_reasons,
                EvidenceRelationship.SUPPORTING,
            ),
            *self._text_evidence(
                data.counter_arguments,
                EvidenceRelationship.CONTRADICTING,
            ),
        ]
        decision_log = self.repo.create(user_id=user_id, data=data, evidence=evidence)
        return self._to_response(decision_log)

    def list_decision_logs(
        self,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-created_at",
        *,
        target_type: TargetType | None = None,
        symbol: str | None = None,
        decision_type: DecisionType | None = None,
        status: DecisionStatus | None = None,
        risk_type: str | None = None,
        review_due_before: datetime | None = None,
    ) -> tuple[list[DecisionLogListItem], int]:
        target_type_value = target_type.value if target_type is not None else None
        decision_type_value = (
            decision_type.value if decision_type is not None else None
        )
        status_value = status.value if status is not None else None
        decision_logs = self.repo.list_by_user(
            user_id,
            offset=offset,
            limit=limit,
            sort=sort,
            target_type=target_type_value,
            symbol=symbol,
            decision_type=decision_type_value,
            status=status_value,
            risk_type=risk_type,
            review_due_before=review_due_before,
        )
        total = self.repo.count_by_user(
            user_id,
            target_type=target_type_value,
            symbol=symbol,
            decision_type=decision_type_value,
            status=status_value,
            risk_type=risk_type,
            review_due_before=review_due_before,
        )
        return self._to_list_items(decision_logs), total

    def get_review_queue(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[DecisionLogListItem], int]:
        now = self._now()
        decision_logs = self.repo.list_review_due(
            user_id,
            now,
            offset=offset,
            limit=limit,
        )
        total = self.repo.count_review_due(user_id, now)
        return self._to_list_items(decision_logs), total

    def get_overview(self, user_id: int) -> DecisionOverviewResponse:
        now = self._now()
        overview = self.repo.aggregate_overview(user_id, now)
        distribution = [
            DecisionTypeDistributionItem(
                type=DecisionType(decision_type),
                count=count,
                share=count / overview.total_count,
            )
            for decision_type, count in overview.decision_type_counts.items()
        ]
        return DecisionOverviewResponse(
            total_count=overview.total_count,
            created_this_week=overview.created_this_week,
            review_due_count=overview.review_due_count,
            active_count=overview.active_count,
            decision_type_distribution=distribution,
            as_of=now,
        )

    def get_decision(
        self,
        decision_log_id: int,
        user_id: int,
    ) -> DecisionLogDetailResponse:
        decision_log = self._get_owned_decision_log(decision_log_id, user_id)
        response = self._to_response(decision_log)
        return DecisionLogDetailResponse(
            **response.model_dump(),
            snapshots=[
                DecisionSnapshotResponse(
                    id=item.id,
                    snapshot_type=item.snapshot_type,
                    data=item.data,
                    captured_at=item.captured_at,
                )
                for item in self.repo.list_snapshots(decision_log.id)
            ],
        )

    def update_draft(
        self,
        decision_log_id: int,
        user_id: int,
        data: DecisionLogUpdate,
    ) -> DecisionLogResponse:
        decision_log = self._get_owned_decision_log(decision_log_id, user_id)
        self._require_draft(decision_log)
        updated_decision_log = self.repo.update(decision_log, data)
        return self._to_response(updated_decision_log)

    def activate(
        self,
        decision_log_id: int,
        user_id: int,
        data: DecisionActivateRequest,
    ) -> DecisionLogResponse:
        decision_log = self._get_owned_decision_log(decision_log_id, user_id)
        self._require_draft(decision_log)
        activated = self.repo.activate(
            decision_log,
            activated_at=self._now(),
            snapshots=data.snapshots,
        )
        return self._to_response(activated)

    def create_review(
        self,
        decision_log_id: int,
        user_id: int,
        data: DecisionReviewCreate,
    ) -> DecisionReviewResponse:
        decision_log = self._get_owned_decision_log(decision_log_id, user_id)
        if decision_log.status == DecisionStatus.DRAFT.value:
            raise AppException(
                status_code=409,
                detail="초안 상태의 의사결정 기록은 복기할 수 없습니다.",
                error_code=ErrorCode.DECISION_LOG_INVALID_STATE,
            )

        reviewed_at = self._now()
        decision_log.status = DecisionStatus.REVIEWED.value
        if decision_log.reviewed_at is None:
            decision_log.reviewed_at = reviewed_at
        review = self.review_repo.create(
            decision_log.id,
            data,
            reviewed_at,
        )
        return self._to_review_response(review)

    def list_reviews(
        self,
        decision_log_id: int,
        user_id: int,
    ) -> list[DecisionReviewResponse]:
        decision_log = self._get_owned_decision_log(decision_log_id, user_id)
        return [
            self._to_review_response(review)
            for review in self.review_repo.list_by_decision(decision_log.id)
        ]

    def _get_owned_decision_log(
        self,
        decision_log_id: int,
        user_id: int,
    ) -> DecisionLog:
        decision_log = self.repo.get_by_id(decision_log_id)
        if decision_log is None:
            raise AppException(
                status_code=404,
                detail="의사결정 기록을 찾을 수 없습니다.",
                error_code=ErrorCode.DECISION_LOG_NOT_FOUND,
            )
        if decision_log.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="의사결정 기록 접근 권한이 없습니다.",
                error_code=ErrorCode.DECISION_LOG_FORBIDDEN,
            )
        return decision_log

    @staticmethod
    def _require_draft(decision_log: DecisionLog) -> None:
        if decision_log.status != DecisionStatus.DRAFT.value:
            raise AppException(
                status_code=409,
                detail="초안 상태의 의사결정 기록만 변경할 수 있습니다.",
                error_code=ErrorCode.DECISION_LOG_INVALID_STATE,
            )

    def _to_response(self, decision_log: DecisionLog) -> DecisionLogResponse:
        return DecisionLogResponse(
            id=decision_log.id,
            user_id=decision_log.user_id,
            target_type=decision_log.target_type,
            target_id=decision_log.target_id,
            symbol=decision_log.symbol,
            decision_type=decision_log.decision_type,
            status=decision_log.status,
            thesis=decision_log.thesis,
            rationale=decision_log.rationale,
            confidence_level=decision_log.confidence_level,
            created_by=decision_log.created_by,
            superseded_by_id=decision_log.superseded_by_id,
            decided_at=decision_log.decided_at,
            activated_at=decision_log.activated_at,
            reviewed_at=decision_log.reviewed_at,
            closed_at=decision_log.closed_at,
            created_at=decision_log.created_at,
            updated_at=decision_log.updated_at,
            evidence=[
                DecisionEvidenceResponse(
                    id=item.id,
                    type=item.evidence_type,
                    evidence_id=item.evidence_id,
                    version=item.evidence_version,
                    title=item.title,
                    summary=item.summary,
                    snapshot=item.snapshot,
                    relationship=item.relationship,
                    created_at=item.created_at,
                )
                for item in self.repo.list_evidence(decision_log.id)
            ],
            risks=[
                DecisionRiskResponse(
                    id=item.id,
                    type=item.risk_type,
                    description=item.description,
                    severity=item.severity,
                    created_at=item.created_at,
                )
                for item in self.repo.list_risks(decision_log.id)
            ],
            review_triggers=[
                DecisionReviewTriggerResponse(
                    id=item.id,
                    type=item.trigger_type,
                    condition=item.condition,
                    scheduled_at=item.scheduled_at,
                    status=item.status,
                    triggered_at=item.triggered_at,
                    created_at=item.created_at,
                )
                for item in self.repo.list_review_triggers(decision_log.id)
            ],
        )

    def _to_list_items(
        self,
        decision_logs: list[DecisionLog],
    ) -> list[DecisionLogListItem]:
        decision_log_ids = [decision_log.id for decision_log in decision_logs]
        risks_by_decision = self.repo.list_risk_types_by_decision(decision_log_ids)
        review_at_by_decision = self.repo.list_review_at_by_decision(decision_log_ids)
        return [
            DecisionLogListItem(
                id=decision_log.id,
                target=DecisionTarget(
                    type=TargetType(decision_log.target_type),
                    id=decision_log.target_id,
                ),
                decision_type=DecisionType(decision_log.decision_type),
                summary=(
                    decision_log.rationale[:SUMMARY_MAX_LENGTH]
                    if decision_log.rationale is not None
                    else None
                ),
                risks=risks_by_decision[decision_log.id],
                confidence_level=(
                    ConfidenceLevel(decision_log.confidence_level)
                    if decision_log.confidence_level is not None
                    else None
                ),
                status=DecisionStatus(decision_log.status),
                review_at=review_at_by_decision.get(decision_log.id),
                created_at=decision_log.created_at,
            )
            for decision_log in decision_logs
        ]

    @staticmethod
    def _to_review_response(review: DecisionReview) -> DecisionReviewResponse:
        return DecisionReviewResponse(
            id=review.id,
            decision_id=review.decision_id,
            outcome_status=OutcomeStatus(review.outcome_status),
            thesis_result=ThesisResult(review.thesis_result),
            process_quality=review.process_quality,
            result_metrics=review.result_metrics,
            what_went_well=review.what_went_well,
            what_was_missed=review.what_was_missed,
            what_to_change=review.what_to_change,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            updated_at=review.updated_at,
        )

    @staticmethod
    def _text_evidence(
        items: list[str],
        relationship: EvidenceRelationship,
    ) -> list[DecisionEvidenceInput]:
        return [
            DecisionEvidenceInput(
                type="USER_MEMO",
                title=item,
                relationship=relationship,
            )
            for item in items
        ]

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)
