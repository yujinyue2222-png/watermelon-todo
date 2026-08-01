"""各类弹窗。

无边框弹窗统一采用「透明外壳 + 不透明圆角面板」结构，
公共部分见 :func:`frontend.dialogs.surface.build_surface`。
"""

from frontend.dialogs.batch_add_dialog import BatchAddDialog, DuplicateChoice
from frontend.dialogs.diy_color_dialog import DiyColorDialog
from frontend.dialogs.due_picker_dialog import DuePickerDialog, Schedule
from frontend.dialogs.export_dialog import ExportOptions, ExportOptionsDialog
from frontend.dialogs.hotkey_dialog import HotkeyDialog
from frontend.dialogs.project_manage_dialog import ProjectManageDialog
from frontend.dialogs.reminder_popup import ReminderPopup
from frontend.dialogs.strong_remind_dialog import StrongRemindDialog
from frontend.dialogs.sync_dialog import SyncDialog, SyncDialogResult
from frontend.dialogs.task_edit_dialog import TaskEditDialog
from frontend.dialogs.theme_market_dialog import ThemeMarketDialog

__all__ = [
    "BatchAddDialog",
    "DiyColorDialog",
    "DuePickerDialog",
    "DuplicateChoice",
    "ExportOptions",
    "ExportOptionsDialog",
    "HotkeyDialog",
    "ProjectManageDialog",
    "ReminderPopup",
    "Schedule",
    "StrongRemindDialog",
    "SyncDialog",
    "SyncDialogResult",
    "TaskEditDialog",
    "ThemeMarketDialog",
]
