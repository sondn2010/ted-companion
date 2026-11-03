"""Khai báo trước MỌI module bảng của các phase sau để chúng không phải sửa file chung này.

Module chưa tồn tại → bỏ qua (debug); lỗi import thật bên trong module → raise.
"""

import importlib
import logging

log = logging.getLogger("ted")

TABLE_MODULES = [
    "src.core.app_state_key_value_store",
    "src.engines.work.rock_model_and_repository",                  # phase 04
    "src.engines.work.calendar_event_cache_model_and_repository",  # phase 05
    # phase 06: QuizItem, ReviewState, Attempt, PlanSnapshot, AgendaDone, WritingSubmission, ProgressReportOutbox
    "src.engines.coach.coach_data_models",
    "src.core.gamification.gamification_table_models",  # gamified hub phase 01
    "src.core.idea_untangle.untangle_session_table_model",  # untangle phase 03
    "src.core.meeting_mode.meeting_session_table_model_and_repository",  # hub phase 13
    "src.core.activity_watcher.activity_table_models",  # activity monitoring & parent reporting
]

for _name in TABLE_MODULES:
    try:
        importlib.import_module(_name)
    except ModuleNotFoundError as e:
        if e.name != _name:
            raise
        log.debug("table module not yet implemented: %s", _name)
