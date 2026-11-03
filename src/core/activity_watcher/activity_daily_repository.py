"""Kho lưu trữ dữ liệu hoạt động hằng ngày (Activity Daily Repository)."""

from datetime import date, datetime, timezone
import json
import logging
from typing import Dict, List, Optional, Tuple
from sqlmodel import Session, select
from src.core.activity_watcher.activity_classifier import ActivityCategory
from src.core.activity_watcher.activity_table_models import DailyActivityRecord

logger = logging.getLogger("ted")


class ActivityDailyRepository:
    def __init__(self, db_engine):
        self._engine = db_engine

    def get_or_create(self, day_str: str, learner: str = "user") -> DailyActivityRecord:
        """Lấy bản ghi của ngày hoặc tạo mới nếu chưa có."""
        with Session(self._engine) as session:
            rec = session.exec(
                select(DailyActivityRecord).where(
                    DailyActivityRecord.date == day_str,
                    DailyActivityRecord.learner == learner,
                )
            ).first()
            if rec is not None:
                return rec

            # Tạo mới
            new_rec = DailyActivityRecord(
                date=day_str,
                learner=learner,
                study_seconds=0,
                distraction_seconds=0,
                neutral_seconds=0,
                unsafe_attempts=0,
                self_corrected_count=0,
                breach_count=0,
                top_apps_json="{}",
                synced_to_hermes=False,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(new_rec)
            session.commit()
            session.refresh(new_rec)
            return new_rec

    def add_tick(
        self,
        day_str: str,
        category: ActivityCategory,
        app_name: str,
        seconds: int = 3,
        learner: str = "user",
    ) -> DailyActivityRecord:
        """Cộng dồn số giây theo phân loại và theo ứng dụng."""
        with Session(self._engine) as session:
            rec = session.exec(
                select(DailyActivityRecord).where(
                    DailyActivityRecord.date == day_str,
                    DailyActivityRecord.learner == learner,
                )
            ).first()
            if rec is None:
                rec = DailyActivityRecord(date=day_str, learner=learner)
                session.add(rec)

            if category == ActivityCategory.STUDY:
                rec.study_seconds += seconds
            elif category == ActivityCategory.DISTRACTION:
                rec.distraction_seconds += seconds
            elif category == ActivityCategory.UNSAFE:
                rec.distraction_seconds += seconds
                rec.unsafe_attempts += 1
            else:
                rec.neutral_seconds += seconds

            # Cập nhật top apps
            try:
                apps: Dict[str, int] = json.loads(rec.top_apps_json or "{}")
            except Exception:
                apps = {}
            if app_name:
                apps[app_name] = apps.get(app_name, 0) + seconds
            rec.top_apps_json = json.dumps(apps, ensure_ascii=False)
            rec.updated_at = datetime.now(timezone.utc)

            session.commit()
            session.refresh(rec)
            return rec

    def record_self_correction(self, day_str: str, learner: str = "user") -> None:
        """Ghi nhận một lần con tự giác quay lại học sau khi bị nhắc."""
        with Session(self._engine) as session:
            rec = session.exec(
                select(DailyActivityRecord).where(
                    DailyActivityRecord.date == day_str,
                    DailyActivityRecord.learner == learner,
                )
            ).first()
            if rec:
                rec.self_corrected_count += 1
                rec.updated_at = datetime.now(timezone.utc)
                session.commit()

    def record_breach(self, day_str: str, learner: str = "user") -> None:
        """Ghi nhận vi phạm xem xao nhãng kéo dài trong giờ học."""
        with Session(self._engine) as session:
            rec = session.exec(
                select(DailyActivityRecord).where(
                    DailyActivityRecord.date == day_str,
                    DailyActivityRecord.learner == learner,
                )
            ).first()
            if rec:
                rec.breach_count += 1
                rec.updated_at = datetime.now(timezone.utc)
                session.commit()

    def mark_synced(self, day_str: str, learner: str = "user") -> None:
        """Đánh dấu bản ghi đã gửi lên não AI Hermes thành công."""
        with Session(self._engine) as session:
            rec = session.exec(
                select(DailyActivityRecord).where(
                    DailyActivityRecord.date == day_str,
                    DailyActivityRecord.learner == learner,
                )
            ).first()
            if rec:
                rec.synced_to_hermes = True
                session.commit()
