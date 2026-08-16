"""后端核心逻辑的单元测试。

运行方式（在 v3 目录下）：

    python -m unittest discover -s tests -v
"""

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from backend.api import TodoBackend
from backend.core.datetime_utils import advance_date, due_label, parse_due
from backend.models.app_config import AppConfig, HotkeySpec
from backend.models.enums import Priority, Recurrence, Remind, TaskStatus
from backend.models.task import StrongRemind, SubTask, Task
from backend.repositories.task_repository import TaskRepository
from backend.services.batch_parser import parse_batch_text, parse_line
from backend.services.export_service import DateRange, StatusFilter
from backend.services.task_service import TaskDraft, TaskQuery
from backend.services.update_service import parse_version


class DateTimeUtilsTest(unittest.TestCase):
    """截止时间工具函数。"""

    def test_parse_due_supports_both_formats(self) -> None:
        day, moment = parse_due("2026-08-05 18:30")
        self.assertEqual(day, datetime.date(2026, 8, 5))
        self.assertEqual(moment, datetime.time(18, 30))

        day, moment = parse_due("2026-08-05")
        self.assertEqual(day, datetime.date(2026, 8, 5))
        self.assertIsNone(moment)

        self.assertEqual(parse_due("不是日期"), (None, None))

    def test_due_label_marks_overdue(self) -> None:
        now = datetime.datetime(2026, 8, 5, 12, 0)
        text, urgent = due_label("2026-08-03", now=now)
        self.assertEqual(text, "已过期 2 天")
        self.assertTrue(urgent)

        text, urgent = due_label("2026-08-06", now=now)
        self.assertEqual(text, "明天")
        self.assertTrue(urgent)

        text, urgent = due_label("2026-09-30", now=now)
        self.assertEqual(text, "09-30")
        self.assertFalse(urgent)

    def test_advance_date_handles_month_end_and_weekend(self) -> None:
        # 1 月 31 日的下一月只有 28 天
        self.assertEqual(
            advance_date(datetime.date(2026, 1, 31), Recurrence.MONTHLY),
            datetime.date(2026, 2, 28),
        )
        # 周五的下一个「工作日」是周一
        friday = datetime.date(2026, 7, 31)
        self.assertEqual(friday.weekday(), 4)
        self.assertEqual(
            advance_date(friday, Recurrence.WORKDAY),
            datetime.date(2026, 8, 3),
        )
        self.assertIsNone(advance_date(friday, Recurrence.NONE))

    def test_monthly_anchor_recovers_after_short_month(self) -> None:
        """月末锚定不能被 2 月带偏：过了 2 月还要回到 31 号。"""
        anchor = 31
        current = datetime.date(2026, 1, 31)
        actual = [current]
        for _ in range(5):
            current = advance_date(current, Recurrence.MONTHLY, anchor)
            actual.append(current)
        self.assertEqual(
            actual,
            [
                datetime.date(2026, 1, 31),
                datetime.date(2026, 2, 28),
                datetime.date(2026, 3, 31),
                datetime.date(2026, 4, 30),
                datetime.date(2026, 5, 31),
                datetime.date(2026, 6, 30),
            ],
        )

    def test_monthly_keeps_mid_month_anchor(self) -> None:
        self.assertEqual(
            advance_date(datetime.date(2026, 1, 15), Recurrence.MONTHLY, 15),
            datetime.date(2026, 2, 15),
        )

    def test_yearly_leap_day_returns_on_next_leap_year(self) -> None:
        """2 月 29 日的年度事项，到了下一个闰年要回到 29 号。"""
        anchor = 29
        current = datetime.date(2024, 2, 29)
        actual = [current]
        for _ in range(4):
            current = advance_date(current, Recurrence.YEARLY, anchor)
            actual.append(current)
        self.assertEqual(actual[-1], datetime.date(2028, 2, 29))
        self.assertEqual(actual[1:4], [datetime.date(year, 2, 28) for year in (2025, 2026, 2027)])

    def test_yearly_keeps_genuine_feb_28(self) -> None:
        """本来就定在 2 月 28 日的，不该被顺手挪到 29 日。"""
        self.assertEqual(
            advance_date(datetime.date(2027, 2, 28), Recurrence.YEARLY, 28),
            datetime.date(2028, 2, 28),
        )


class BatchParserTest(unittest.TestCase):
    """批量粘贴解析。"""

    def test_parse_full_columns(self) -> None:
        parsed = parse_line("完成周报｜P1｜08-05｜补充关键数据", today=datetime.date(2026, 7, 31))
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.text, "完成周报")
        self.assertEqual(parsed.priority, Priority.P1)
        self.assertEqual(parsed.due, "2026-08-05")
        self.assertEqual(parsed.note, "补充关键数据")

    def test_second_column_falls_back_to_note(self) -> None:
        parsed = parse_line("对齐需求 | 找产品确认口径")
        self.assertEqual(parsed.priority, "")
        self.assertEqual(parsed.note, "找产品确认口径")

    def test_relative_dates_and_bullets(self) -> None:
        today = datetime.date(2026, 7, 31)  # 周五
        parsed = parse_line("- 评审设计稿\t明天", today=today)
        self.assertEqual(parsed.text, "评审设计稿")
        self.assertEqual(parsed.due, "2026-08-01")

        # 基准日是周五，下一个自然周是 08-03（周一）到 08-09（周日）
        parsed = parse_line("1. 周会 | 下周一", today=today)
        self.assertEqual(parsed.text, "周会")
        self.assertEqual(parsed.due, "2026-08-03")

    def test_blank_lines_are_skipped(self) -> None:
        self.assertIsNone(parse_line("   "))
        self.assertEqual(len(parse_batch_text("甲\n\n乙\n  \n丙")), 3)

    def test_next_week_lands_in_the_actual_next_week(self) -> None:
        """「下周X」必须落在下一个自然周内，不能因为取模再加 7 而跳两周。"""
        friday = datetime.date(2026, 7, 31)
        self.assertEqual(friday.weekday(), 4)
        expected = {
            "一": "2026-08-03",
            "二": "2026-08-04",
            "三": "2026-08-05",
            "四": "2026-08-06",
            "五": "2026-08-07",
            "六": "2026-08-08",
            "日": "2026-08-09",
        }
        for weekday, due in expected.items():
            parsed = parse_line(f"周会 | 下周{weekday}", today=friday)
            self.assertEqual(parsed.due, due, f"下周{weekday}")

    def test_plain_weekday_means_the_coming_one(self) -> None:
        friday = datetime.date(2026, 7, 31)
        self.assertEqual(parse_line("甲 | 周一", today=friday).due, "2026-08-03")
        self.assertEqual(parse_line("甲 | 周五", today=friday).due, "2026-07-31")

    def test_legacy_priority_is_recognized(self) -> None:
        """从 v2 复制来的「紧急」要能认出来，且不能吃掉后面的日期列。"""
        parsed = parse_line("写周报|紧急|2026-08-05")
        self.assertEqual(parsed.text, "写周报")
        self.assertEqual(parsed.priority, Priority.P1)
        self.assertEqual(parsed.due, "2026-08-05")
        self.assertEqual(parsed.note, "")


class TaskServiceTest(unittest.TestCase):
    """待办服务。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.backend = TodoBackend(
            data_path=root / "todo_data.json",
            config_path=root / "todo_config.json",
            migrate_legacy=False,
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_create_and_persist(self) -> None:
        self.backend.tasks.create(TaskDraft(text="写周报", category="工作"))
        root = Path(self._temp.name)
        reloaded = TodoBackend(
            data_path=root / "todo_data.json",
            config_path=root / "todo_config.json",
            migrate_legacy=False,
        )
        self.assertEqual([task.text for task in reloaded.tasks.tasks], ["写周报"])

    def test_query_sorts_pinned_and_done(self) -> None:
        service = self.backend.tasks
        normal = service.create(TaskDraft(text="普通事项"))
        pinned = service.create(TaskDraft(text="置顶事项"))
        service.create(TaskDraft(text="紧急事项", priority=Priority.P0))
        finished = service.create(TaskDraft(text="已完成事项"))

        service.set_pinned(pinned.id, True)
        service.toggle_status(finished.id)

        ordered = [task.text for task in service.query(TaskQuery())]
        self.assertEqual(ordered[0], "置顶事项")
        self.assertEqual(ordered[1], "紧急事项")
        self.assertEqual(ordered[-1], "已完成事项")
        self.assertIn(normal.text, ordered)

    def test_query_separates_daily_and_project(self) -> None:
        service = self.backend.tasks
        service.create(TaskDraft(text="日常事项"))
        service.create(TaskDraft(text="项目事项", project="Q3 增长"))

        daily = service.query(TaskQuery(view="daily"))
        self.assertEqual([task.text for task in daily], ["日常事项"])

        project = service.query(TaskQuery(view="project", project="Q3 增长"))
        self.assertEqual([task.text for task in project], ["项目事项"])

    def test_completing_recurring_task_spawns_next(self) -> None:
        service = self.backend.tasks
        task = service.create(
            TaskDraft(text="每日站会", due="2026-08-05 10:00", recur=Recurrence.DAILY)
        )
        service.toggle_status(task.id)

        dues = sorted(item.due for item in service.tasks)
        self.assertEqual(dues, ["2026-08-05 10:00", "2026-08-06 10:00"])

    def test_recurring_task_stops_after_end_date(self) -> None:
        service = self.backend.tasks
        task = service.create(
            TaskDraft(
                text="冲刺",
                due="2026-08-05",
                recur=Recurrence.DAILY,
                recur_end="2026-08-05",
            )
        )
        service.toggle_status(task.id)
        self.assertEqual(len(service.tasks), 1)

    def test_create_many_respects_duplicate_choice(self) -> None:
        service = self.backend.tasks
        drafts = [TaskDraft(text="重复项", project="P"), TaskDraft(text="新项", project="P")]
        service.create_many(drafts)

        skipped = service.create_many(drafts, skip_duplicates=True)
        self.assertEqual(skipped.created_count, 0)
        self.assertEqual(skipped.skipped, 2)

        forced = service.create_many(drafts, skip_duplicates=False)
        self.assertEqual(forced.created_count, 2)

    def test_batch_operations(self) -> None:
        service = self.backend.tasks
        first = service.create(TaskDraft(text="甲"))
        second = service.create(TaskDraft(text="乙"))

        self.assertEqual(service.set_category_many([first.id, second.id], "学习"), 2)
        self.assertEqual(service.set_status_many([first.id], TaskStatus.DONE), 1)
        self.assertEqual(service.clear_completed(), 1)
        self.assertEqual([task.text for task in service.tasks], ["乙"])

    def test_subtasks_toggle(self) -> None:
        service = self.backend.tasks
        task = service.create(TaskDraft(text="大事"))
        service.replace_subtasks(task.id, [SubTask("第一步"), SubTask("第二步")])
        service.toggle_subtask(task.id, 1)

        updated = service.get(task.id)
        self.assertEqual(updated.subtask_progress(), (1, 2))

    def test_update_ignores_unknown_field(self) -> None:
        task = self.backend.tasks.create(TaskDraft(text="甲"))
        self.backend.tasks.update(task.id, text="乙", nonexistent="x")
        self.assertEqual(self.backend.tasks.get(task.id).text, "乙")

    def test_changing_due_resets_per_deadline_bookkeeping(self) -> None:
        """改了截止时间就得清掉按上一个截止时间记的账，否则提醒会哑火。"""
        service = self.backend.tasks
        task = service.create(TaskDraft(text="交材料", due="2026-08-05 18:00"))
        task.remind_log.append("ahead")
        task.notified = True
        task.strong.count = 3
        task.strong.last = "2026-08-05T17:00:00"

        service.update(task.id, due="2026-08-12 18:00")

        updated = service.get(task.id)
        self.assertEqual(updated.remind_log, [])
        self.assertFalse(updated.notified)
        self.assertEqual(updated.strong.count, 0)
        self.assertIsNone(updated.strong.last)

    def test_unchanged_due_keeps_bookkeeping(self) -> None:
        """只改标题时不该顺手把「已提醒过」清掉，否则会重复打扰。"""
        service = self.backend.tasks
        task = service.create(TaskDraft(text="交材料", due="2026-08-05 18:00"))
        task.remind_log.append("ahead")

        service.update(task.id, text="交材料（终稿）")
        self.assertEqual(service.get(task.id).remind_log, ["ahead"])

    def test_monthly_recurrence_chain_keeps_month_end(self) -> None:
        """连续完成月末循环待办，日期不能一路退到 28 号。"""
        service = self.backend.tasks
        service.create(
            TaskDraft(text="月末对账", due="2026-01-31", recur=Recurrence.MONTHLY)
        )
        seen = []
        for _ in range(4):
            pending = [item for item in service.tasks if not item.is_done]
            self.assertEqual(len(pending), 1)
            seen.append(pending[0].due)
            service.toggle_status(pending[0].id)
        self.assertEqual(seen, ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"])

    def test_touch_timestamp_is_strictly_increasing(self) -> None:
        """同一毫秒内连改两次，时间戳必须往前走，否则服务端会丢掉第二次。"""
        service = self.backend.tasks
        task = service.create(TaskDraft(text="甲"))
        stamps = []
        for index in range(5):
            service.update(task.id, text=f"甲{index}")
            stamps.append(service.get(task.id).updated_at)
        self.assertEqual(stamps, sorted(set(stamps)))


class StatsServiceTest(unittest.TestCase):
    """今日统计口径。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.backend = TodoBackend(
            data_path=root / "data.json",
            config_path=root / "config.json",
            migrate_legacy=False,
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_today_excludes_future_and_project_tasks(self) -> None:
        service = self.backend.tasks
        today = datetime.date(2026, 8, 5)
        service.create(TaskDraft(text="没填日期"))
        service.create(TaskDraft(text="今天到期", due="2026-08-05"))
        service.create(TaskDraft(text="已过期", due="2026-08-01", priority=Priority.P0))
        service.create(TaskDraft(text="明天到期", due="2026-08-06"))
        service.create(TaskDraft(text="项目待办", project="P", due="2026-08-05"))

        summary = self.backend.stats.today(today=today)
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.done, 0)
        self.assertEqual(summary.urgent, 1)
        self.assertEqual(summary.percent, 0)

    def test_project_summary(self) -> None:
        service = self.backend.tasks
        first = service.create(TaskDraft(text="甲", project="P"))
        service.create(TaskDraft(text="乙", project="P"))
        service.toggle_status(first.id)

        summary = self.backend.projects.summary("P")
        self.assertEqual((summary.total, summary.done, summary.percent), (2, 1, 50))


class ProjectServiceTest(unittest.TestCase):
    """项目服务。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.backend = TodoBackend(
            data_path=root / "data.json",
            config_path=root / "config.json",
            migrate_legacy=False,
        )
        self.backend.tasks.create(TaskDraft(text="甲", project="旧项目"))
        self.backend.tasks.create(TaskDraft(text="乙", project="旧项目"))
        self.backend.tasks.create(TaskDraft(text="丙", project="别的项目"))

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_names_are_unique_and_ordered(self) -> None:
        self.assertEqual(self.backend.projects.names(), ["旧项目", "别的项目"])

    def test_rename_and_delete(self) -> None:
        self.assertEqual(self.backend.projects.rename("旧项目", "新项目"), 2)
        self.assertEqual(self.backend.projects.names(), ["新项目", "别的项目"])
        self.assertEqual(self.backend.projects.delete("新项目"), 2)
        self.assertEqual(self.backend.projects.names(), ["别的项目"])


class ReminderServiceTest(unittest.TestCase):
    """提醒判定。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.backend = TodoBackend(
            data_path=root / "data.json",
            config_path=root / "config.json",
            migrate_legacy=False,
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_ahead_and_due_fire_once(self) -> None:
        self.backend.tasks.create(
            TaskDraft(
                text="提交材料",
                due="2026-08-05 18:00",
                remind=Remind.BEFORE_30_MIN,
            )
        )
        ahead = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 17, 40))
        self.assertEqual([event.kind for event in ahead], ["ahead"])
        self.assertIn("30 分钟", ahead[0].phrase)

        # 同一档位不会重复提醒
        again = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 17, 50))
        self.assertEqual(again, [])

        due = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 18, 30))
        self.assertEqual([event.kind for event in due], ["due"])
        self.assertTrue(due[0].urgent)

    def test_reminder_off_never_fires(self) -> None:
        self.backend.tasks.create(
            TaskDraft(text="随便", due="2026-08-05", remind=Remind.OFF)
        )
        self.assertEqual(
            self.backend.reminders.collect(now=datetime.datetime(2026, 8, 6, 9, 0)), []
        )

    def test_strong_remind_respects_interval_and_limit(self) -> None:
        task = self.backend.tasks.create(TaskDraft(text="交方案", due="2026-08-05 18:00"))
        self.backend.tasks.set_strong_remind(
            task.id,
            StrongRemind(
                enabled=True,
                before_value=2,
                before_unit="小时",
                interval_value=30,
                interval_unit="分钟",
                max_count=2,
                float_window=True,
            ),
        )

        first = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 16, 30))
        self.assertEqual([event.kind for event in first], ["strong"])

        # 间隔未到不再提醒
        self.assertEqual(
            self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 16, 40)), []
        )

        second = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 17, 5))
        self.assertEqual([event.kind for event in second], ["strong"])

        # 已达 2 次上限
        self.assertEqual(
            self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 17, 45)), []
        )

    def test_done_task_is_never_reminded(self) -> None:
        task = self.backend.tasks.create(TaskDraft(text="已完成", due="2026-08-05"))
        self.backend.tasks.toggle_status(task.id)
        self.assertEqual(
            self.backend.reminders.collect(now=datetime.datetime(2026, 8, 6, 9, 0)), []
        )

    def test_on_day_reminder_fires_in_the_morning(self) -> None:
        """只填日期时，「到期当天」要在当天白天响，而不是拖到 23:59。"""
        self.backend.tasks.create(
            TaskDraft(text="交材料", due="2026-08-05", remind=Remind.ON_TIME)
        )
        events = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 9, 30))
        self.assertEqual([event.kind for event in events], ["ahead"])
        self.assertEqual(events[0].phrase, "今天到期")

    def test_on_day_reminder_waits_for_explicit_time(self) -> None:
        """填了具体时间点时，「到期当天」仍应到点才响。"""
        self.backend.tasks.create(
            TaskDraft(text="开会", due="2026-08-05 15:00", remind=Remind.ON_TIME)
        )
        self.assertEqual(
            self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 9, 30)), []
        )
        events = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 15, 0))
        self.assertEqual([event.kind for event in events], ["due"])

    def test_strong_remind_revives_after_reschedule(self) -> None:
        """次数用尽后改期，强提醒必须重新开始，而不是永远哑火。"""
        task = self.backend.tasks.create(TaskDraft(text="交方案", due="2026-08-05 18:00"))
        self.backend.tasks.set_strong_remind(
            task.id,
            StrongRemind(
                enabled=True,
                before_value=2,
                before_unit="小时",
                interval_value=30,
                interval_unit="分钟",
                max_count=1,
                float_window=True,
            ),
        )
        fired = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 16, 30))
        self.assertEqual([event.kind for event in fired], ["strong"])
        self.assertTrue(self.backend.tasks.get(task.id).strong.reached_limit())

        self.backend.tasks.update(task.id, due="2026-08-12 18:00")

        revived = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 12, 16, 30))
        self.assertEqual([event.kind for event in revived], ["strong"])

    def test_reminder_bookkeeping_does_not_trigger_sync(self) -> None:
        """「已提醒过」不参与同步，不该惊动本地改动回调去安排一次空同步。"""
        task = self.backend.tasks.create(
            TaskDraft(text="交材料", due="2026-08-05 18:00", remind=Remind.BEFORE_30_MIN)
        )
        # 装作这条已经同步过，这样剩下的脏标记只可能来自提醒记账
        self.backend.tasks.mark_synced({task.id: task.updated_at})
        calls = []
        self.backend.tasks.set_change_listener(lambda: calls.append(1))

        events = self.backend.reminders.collect(now=datetime.datetime(2026, 8, 5, 17, 40))
        self.assertEqual([event.kind for event in events], ["ahead"])
        self.assertEqual(calls, [])
        self.assertEqual(self.backend.tasks.dirty_records(), [])


class ExportServiceTest(unittest.TestCase):
    """导出。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.backend = TodoBackend(
            data_path=self.root / "data.json",
            config_path=self.root / "config.json",
            migrate_legacy=False,
        )

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_export_csv(self) -> None:
        self.backend.tasks.create(
            TaskDraft(text="写文档", category="工作", due="2026-08-05", note="带上数据")
        )
        target = self.root / "out.csv"
        count = self.backend.exporter.export(target, self.backend.tasks.tasks)

        self.assertEqual(count, 1)
        content = target.read_text(encoding="utf-8-sig")
        self.assertIn("状态,待办内容", content)
        self.assertIn("未完成,写文档,工作", content)

    def test_export_txt_with_header(self) -> None:
        self.backend.tasks.create(TaskDraft(text="读书"))
        target = self.root / "out.txt"
        self.backend.exporter.export(
            target, self.backend.tasks.tasks, header_lines=["导出范围：不限"]
        )
        content = target.read_text(encoding="utf-8")
        self.assertIn("导出范围：不限", content)
        self.assertIn("[ ] 读书", content)

    def test_filter_by_status_and_range(self) -> None:
        service = self.backend.tasks
        done = service.create(TaskDraft(text="已完成", due="2026-08-01"))
        service.create(TaskDraft(text="未完成", due="2026-08-10"))
        service.toggle_status(done.id)

        only_done = self.backend.exporter.filter_tasks(
            service.tasks, status=StatusFilter.DONE
        )
        self.assertEqual([task.text for task in only_done], ["已完成"])

        in_range = self.backend.exporter.filter_tasks(
            service.tasks, date_range=DateRange(start="2026-08-05", end="2026-08-31")
        )
        self.assertEqual([task.text for task in in_range], ["未完成"])


class ConfigTest(unittest.TestCase):
    """配置模型与旧数据兼容。"""

    def test_round_trip(self) -> None:
        config = AppConfig()
        config.theme = "曜石黑"
        config.add_category("副业")
        restored = AppConfig.from_dict(config.to_dict())
        self.assertEqual(restored.theme, "曜石黑")
        self.assertIn("副业", restored.categories)
        self.assertEqual(restored.geometry.to_list(), config.geometry.to_list())

    def test_legacy_keys(self) -> None:
        restored = AppConfig.from_dict(
            {
                "custom_theme": {"accent": "#123456"},
                "bg_image": "/tmp/bg.png",
                "hotkey": {"ctrl": False, "alt": False, "shift": False, "key": "k"},
                "geometry": "坏数据",
            }
        )
        self.assertIn("自定义", restored.custom_themes)
        self.assertEqual(restored.background_image, "/tmp/bg.png")
        # 一个修饰键都没勾时自动补回默认组合
        self.assertEqual(restored.hotkey.label(), "Ctrl+Alt+K")
        self.assertEqual(restored.geometry.to_list(), [140, 120, 340, 500])

    def test_hotkey_mac_label(self) -> None:
        config = AppConfig()
        self.assertEqual(config.hotkey.label(mac_style=True), "⌘⌥T")

    def test_hotkey_key_is_cleaned_in_both_branches(self) -> None:
        """没勾修饰键的那条分支同样要清洗主键，否则脏值会被写进配置。"""
        spec = HotkeySpec(ctrl=False, alt=False, shift=False, key="  t  ").normalized()
        self.assertEqual(spec.key, "T")
        self.assertEqual(HotkeySpec(ctrl=False, alt=False, shift=False, key="").normalized().key, "T")

    def test_custom_theme_is_written_back_for_v2(self) -> None:
        """v2 的旧键要回写，两个版本共用配置文件时 DIY 配色才不会丢。"""
        config = AppConfig()
        config.custom_themes["自定义"] = {"accent": "#123456"}
        self.assertEqual(config.to_dict()["custom_theme"], {"accent": "#123456"})


class TaskModelTest(unittest.TestCase):
    """模型迁移。"""

    def test_legacy_priority_and_missing_fields(self) -> None:
        task = Task.from_dict({"id": "1", "text": "旧数据", "priority": "紧急"})
        self.assertEqual(task.priority, Priority.P1)
        self.assertEqual(task.remind, Remind.DEFAULT)
        self.assertEqual(task.note, "")
        self.assertFalse(task.strong.enabled)
        self.assertTrue(task.is_daily)

    def test_round_trip_keeps_subtasks(self) -> None:
        task = Task.from_dict(
            {
                "id": "1",
                "text": "带步骤",
                "subtasks": [{"text": "第一步", "done": True}, "坏数据"],
            }
        )
        self.assertEqual(task.subtask_progress(), (1, 1))
        self.assertEqual(Task.from_dict(task.to_dict()).subtask_progress(), (1, 1))

    def test_malformed_field_types_do_not_raise(self) -> None:
        """字段值类型坏掉时要能兜住：一条坏记录不该让程序开不了。"""
        for broken in (
            {"id": "1", "text": "甲", "subtasks": 5},
            {"id": "2", "text": "乙", "remind_log": 7},
            {"id": "3", "text": "丙", "remind_log": "ahead"},
            {"id": "4", "text": "丁", "strong": ["坏数据"]},
            {"id": "5", "text": "戊", "strong": "坏数据"},
        ):
            task = Task.from_dict(broken)
            self.assertEqual(task.subtasks, [])
            # 字符串不能被逐字符拆成 ['a','h','e','a','d']
            self.assertEqual(task.remind_log, [])
            self.assertFalse(task.strong.enabled)

    def test_strong_last_of_wrong_type_is_ignored(self) -> None:
        """last 存成数字时 fromisoformat 抛的是 TypeError，必须一起兜住。"""
        task = Task.from_dict({"id": "1", "text": "甲", "strong": {"last": 1754000000000}})
        self.assertIsNone(task.strong.last_at)


class TaskRepositoryTest(unittest.TestCase):
    """数据文件的容错读取。"""

    def test_broken_record_is_skipped_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.json"
            path.write_text(
                json.dumps(
                    [
                        {"id": "1", "text": "好记录"},
                        {"id": "2", "text": "坏记录", "strong": ["炸"]},
                        "根本不是对象",
                    ]
                ),
                encoding="utf-8",
            )
            tasks = TaskRepository(path).load()
        self.assertEqual([task.text for task in tasks], ["好记录", "坏记录"])


class UpdateServiceTest(unittest.TestCase):
    """版本号比较。"""

    def test_prerelease_is_not_newer_than_release(self) -> None:
        """v3.7-rc1 不能被解析成 (3, 71)，那会比 3.8 还「新」。"""
        self.assertEqual(parse_version("v3.7"), (3, 7))
        self.assertEqual(parse_version("v3.7-beta"), (3, 7))
        self.assertEqual(parse_version("v3.7-rc1"), (3, 7))
        self.assertEqual(parse_version("v3.7-beta2"), (3, 7))
        self.assertEqual(parse_version("3.7.1"), (3, 7, 1))
        self.assertLess(parse_version("v3.7-rc1"), parse_version("3.8"))

    def test_non_ascii_digits_do_not_raise(self) -> None:
        self.assertEqual(parse_version("v3.7\u00b2"), (3, 7))


if __name__ == "__main__":
    unittest.main()
