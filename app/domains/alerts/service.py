from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.alerts.model import Alert
from app.domains.alerts.repository import AlertRepository
from app.domains.alerts.schema import AlertCreate, AlertResponse
from app.domains.alerts.types import AlertStatus
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository


class AlertService:
    def __init__(self, db: Session) -> None:
        self.repo = AlertRepository(db)
        self.signal_repo = SignalRepository(db)
        self.asset_repo = AssetRepository(db)

    def create_alert(self, user_id: int, signal: Signal) -> Alert | None:
        return self.repo.create_if_absent(
            AlertCreate(
                user_id=user_id,
                signal_id=signal.id,
                dedup_key=self._dedup_key(signal),
            )
        )

    def list_alerts(
        self,
        user_id: int,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Alert]:
        return self.repo.list_by_user(
            user_id,
            status,
            offset=offset,
            limit=limit,
        )

    def list_alert_responses(
        self,
        user_id: int,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[AlertResponse]:
        return self.build_alert_responses(
            self.list_alerts(
                user_id,
                status,
                offset=offset,
                limit=limit,
            )
        )

    def count_alerts(self, user_id: int, status: str | None = None) -> int:
        return self.repo.count_by_user(user_id, status)

    def mark_read(self, alert_id: int, user_id: int) -> Alert:
        return self._update_owned_alert(alert_id, user_id, AlertStatus.READ.value)

    def mark_read_response(self, alert_id: int, user_id: int) -> AlertResponse:
        return self.build_alert_response(self.mark_read(alert_id, user_id))

    def dismiss(self, alert_id: int, user_id: int) -> Alert:
        return self._update_owned_alert(alert_id, user_id, AlertStatus.DISMISSED.value)

    def dismiss_response(self, alert_id: int, user_id: int) -> AlertResponse:
        return self.build_alert_response(self.dismiss(alert_id, user_id))

    def build_alert_response(self, alert: Alert) -> AlertResponse:
        return self.build_alert_responses([alert])[0]

    def build_alert_responses(self, alerts: list[Alert]) -> list[AlertResponse]:
        signal_ids = {alert.signal_id for alert in alerts}
        signals = {
            signal.id: signal
            for signal in [
                self.signal_repo.get_by_id(signal_id) for signal_id in signal_ids
            ]
            if signal is not None
        }
        asset_ids = {signal.asset_id for signal in signals.values()}
        assets = {
            asset.id: asset
            for asset in [self.asset_repo.get_by_id(asset_id) for asset_id in asset_ids]
            if asset is not None
        }

        return [
            self._build_alert_response(
                alert,
                signal=signals.get(alert.signal_id),
                assets=assets,
            )
            for alert in alerts
        ]

    def _update_owned_alert(self, alert_id: int, user_id: int, status: str) -> Alert:
        alert = self.repo.get_by_id(alert_id)
        if alert is None or alert.user_id != user_id:
            raise AppException(
                status_code=404,
                detail="알림을 찾을 수 없습니다.",
                error_code=ErrorCode.ALERT_NOT_FOUND,
            )
        return self.repo.update_status(alert, status)

    def _build_alert_response(
        self,
        alert: Alert,
        signal: Signal | None,
        assets: dict[int, Asset],
    ) -> AlertResponse:
        asset = assets.get(signal.asset_id) if signal is not None else None
        return AlertResponse(
            id=alert.id,
            user_id=alert.user_id,
            signal_id=alert.signal_id,
            status=alert.status,
            created_at=alert.created_at,
            asset_id=signal.asset_id if signal is not None else None,
            symbol=asset.symbol if asset is not None else None,
            alert_type=signal.signal_type if signal is not None else None,
            message=signal.reason if signal is not None else None,
        )

    def _dedup_key(self, signal: Signal) -> str:
        if signal.news_item_id is not None:
            return f"{signal.signal_type}:{signal.news_item_id}"
        return f"{signal.signal_type}:signal:{signal.id}"
