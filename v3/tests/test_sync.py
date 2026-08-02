"""多端同步的端到端测试。

真的把同步服务跑起来（监听随机端口），再用两个独立的 ``TodoBackend``
模拟「电脑」和「手机」，验证新增、修改、删除、冲突在两端之间的传播。

运行方式（在 v3 目录下）：

    python -m unittest tests.test_sync -v
"""

import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from backend.api import TodoBackend
from backend.models.task import SubTask, now_ms
from backend.services.task_service import TOMBSTONE_KEEP_DAYS, TaskDraft
from backend.sync.client import SyncClient, SyncError
from backend.sync.identity import generate_sync_code, is_valid_sync_code
from server.database import SyncDatabase
from server.http_api import create_server

_MS_PER_DAY = 24 * 3600 * 1000


class SyncTestBase(unittest.TestCase):
    """起一个真实的同步服务，并提供构造客户端的辅助方法。"""

    server: Optional[ThreadingHTTPServer] = None

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.database = SyncDatabase(self.root / "server" / "sync.db")
        # 端口传 0 让系统分配空闲端口，避免测试之间抢端口
        self.server = create_server("127.0.0.1", 0, self.database)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.sync_code = generate_sync_code()

    def tearDown(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        self._thread.join(timeout=5)
        self._temp.cleanup()

    def make_client(self, name: str, sync_code: Optional[str] = None) -> TodoBackend:
        """造一个已配置好同步的独立客户端。

        Args:
            name: 客户端名字，用于隔离数据目录。
            sync_code: 同步码；默认用本次测试的共享同步码。
        """
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        backend = TodoBackend(
            data_path=folder / "todo_data.json",
            config_path=folder / "todo_config.json",
            migrate_legacy=False,
        )
        backend.config.sync.enabled = True
        backend.config.sync.server_url = self.base_url
        backend.config.sync.user_id = sync_code or self.sync_code
        backend.save_config()
        return backend


class ServerApiTest(SyncTestBase):
    """服务端接口。"""

    def test_health(self) -> None:
        payload = SyncClient(self.base_url).health()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["users"], 0)
        self.assertFalse(payload["auth_required"])

    def test_rejects_invalid_sync_code(self) -> None:
        client = SyncClient(self.base_url)
        with self.assertRaises(SyncError) as context:
            client.sync("bad code!", 0, [])
        self.assertIn("400", str(context.exception))

    def test_unknown_endpoint(self) -> None:
        with self.assertRaises(SyncError):
            SyncClient(self.base_url)._request("/api/nope", payload={"a": 1})

    def test_sync_code_format(self) -> None:
        self.assertTrue(is_valid_sync_code(generate_sync_code()))
        self.assertFalse(is_valid_sync_code("short"))
        self.assertFalse(is_valid_sync_code("has space"))


class StaticFileSecurityTest(unittest.TestCase):
    """静态网页托管的目录穿越防护。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.database = SyncDatabase(root / "sync.db")

        web_root = root / "web"
        web_root.mkdir()
        (web_root / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
        (web_root / "有 空格.txt").write_text("decoded", encoding="utf-8")
        # 和 web_root 同前缀的兄弟目录：字符串前缀判断会把它误放行
        sibling = root / "web-secret"
        sibling.mkdir()
        (sibling / "passwd").write_text("TOP-SECRET", encoding="utf-8")

        self.server = create_server("127.0.0.1", 0, self.database, web_root=web_root)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)
        self._temp.cleanup()

    def _get(self, path: str) -> tuple[int, bytes]:
        """发一个不做路径规范化的原始 GET，返回 (状态码, 正文)。"""
        connection = HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            connection.putrequest("GET", path, skip_host=False, skip_accept_encoding=True)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_serves_index(self) -> None:
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"ok", body)

    def test_percent_encoded_names_are_decoded(self) -> None:
        status, body = self._get("/%E6%9C%89%20%E7%A9%BA%E6%A0%BC.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"decoded")

    def test_rejects_parent_directory_traversal(self) -> None:
        status, body = self._get("/../../etc/passwd")
        self.assertEqual(status, 403)
        self.assertNotIn(b"root:", body)

    def test_rejects_sibling_directory_with_shared_prefix(self) -> None:
        """/opt/app/web-secret 不在 /opt/app/web 里，必须按路径层级判断。"""
        status, body = self._get("/../web-secret/passwd")
        self.assertEqual(status, 403)
        self.assertNotIn(b"TOP-SECRET", body)

    def test_rejects_encoded_traversal(self) -> None:
        status, body = self._get("/%2e%2e/web-secret/passwd")
        self.assertEqual(status, 403)
        self.assertNotIn(b"TOP-SECRET", body)


class AccessTokenTest(unittest.TestCase):
    """配置了访问令牌后的鉴权。"""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.database = SyncDatabase(Path(self._temp.name) / "sync.db")
        self.token = "s3cret-token"
        self.server = create_server("127.0.0.1", 0, self.database, access_token=self.token)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=5)
        self._temp.cleanup()

    def test_health_requires_token(self) -> None:
        """健康检查会暴露用户数与库大小，配了令牌就不该匿名可读。"""
        with self.assertRaises(SyncError):
            SyncClient(self.base_url).health()

    def test_health_passes_with_token(self) -> None:
        payload = SyncClient(self.base_url, self.token).health()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["auth_required"])

    def test_sync_requires_token(self) -> None:
        with self.assertRaises(SyncError):
            SyncClient(self.base_url).sync(generate_sync_code(), 0, [])


class TwoDeviceSyncTest(SyncTestBase):
    """两台设备之间的数据传播。"""

    def test_new_task_propagates(self) -> None:
        desktop = self.make_client("desktop")
        phone = self.make_client("phone")

        desktop.tasks.create(TaskDraft(text="买西瓜", category="生活"))
        result = desktop.sync.sync_now()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.pushed, 1)

        pulled = phone.sync.sync_now()
        self.assertTrue(pulled.ok, pulled.error)
        self.assertEqual([task.text for task in phone.tasks.tasks], ["买西瓜"])
        self.assertEqual(phone.tasks.tasks[0].category, "生活")

    def test_edit_propagates_both_ways(self) -> None:
        desktop = self.make_client("desktop")
        phone = self.make_client("phone")

        task = desktop.tasks.create(TaskDraft(text="写周报"))
        desktop.sync.sync_now()
        phone.sync.sync_now()

        # 手机上改标题并完成
        phone_task = phone.tasks.tasks[0]
        phone.tasks.update(phone_task.id, text="写周报（已补数据）")
        phone.tasks.toggle_status(phone_task.id)
        phone.sync.sync_now()

        desktop.sync.sync_now()
        updated = desktop.tasks.get(task.id)
        self.assertEqual(updated.text, "写周报（已补数据）")
        self.assertTrue(updated.is_done)

    def test_delete_propagates_and_does_not_resurrect(self) -> None:
        desktop = self.make_client("desktop")
        phone = self.make_client("phone")

        task = desktop.tasks.create(TaskDraft(text="退掉订阅"))
        desktop.sync.sync_now()
        phone.sync.sync_now()
        self.assertEqual(len(phone.tasks.tasks), 1)

        desktop.tasks.delete(task.id)
        desktop.sync.sync_now()

        phone.sync.sync_now()
        self.assertEqual(phone.tasks.tasks, [])
        # 墓碑仍在本地，保证再同步也不会被复活
        self.assertTrue(phone.tasks.all_records()[0].deleted)

        # 再来回同步几次也不该冒出来
        phone.sync.sync_now()
        desktop.sync.sync_now()
        self.assertEqual(phone.tasks.tasks, [])
        self.assertEqual(desktop.tasks.tasks, [])

    def test_conflict_resolves_to_latest_edit(self) -> None:
        desktop = self.make_client("desktop")
        phone = self.make_client("phone")

        task = desktop.tasks.create(TaskDraft(text="原始标题"))
        desktop.sync.sync_now()
        phone.sync.sync_now()

        # 两端离线各改一次：手机改得更晚，应该胜出
        desktop_task = desktop.tasks.get(task.id)
        desktop_task.text = "电脑改的"
        desktop_task.updated_at = now_ms() - 5000
        desktop_task.dirty = True
        desktop.tasks.save()

        phone_task = phone.tasks.get(task.id)
        phone_task.text = "手机改的"
        phone_task.updated_at = now_ms()
        phone_task.dirty = True
        phone.tasks.save()

        desktop.sync.sync_now()
        phone.sync.sync_now()
        desktop.sync.sync_now()

        self.assertEqual(desktop.tasks.get(task.id).text, "手机改的")
        self.assertEqual(phone.tasks.get(task.id).text, "手机改的")

    def test_same_millisecond_conflict_converges(self) -> None:
        """两端在同一毫秒改同一条待办时必须收敛，不能各执己见永久分叉。

        服务端在时间戳打平时判自己赢，所以客户端也必须在打平时接受远端版本。
        """
        desktop = self.make_client("desktop")
        phone = self.make_client("phone")

        task = desktop.tasks.create(TaskDraft(text="原始标题"))
        desktop.sync.sync_now()
        phone.sync.sync_now()

        stamp = now_ms()
        for backend, text in ((desktop, "电脑改的"), (phone, "手机改的")):
            edited = backend.tasks.get(task.id)
            edited.text = text
            edited.updated_at = stamp
            edited.dirty = True
            backend.tasks.save()

        for _ in range(3):
            desktop.sync.sync_now()
            phone.sync.sync_now()

        self.assertEqual(desktop.tasks.get(task.id).text, phone.tasks.get(task.id).text)
        self.assertEqual(desktop.tasks.dirty_records(), [])
        self.assertEqual(phone.tasks.dirty_records(), [])

    def test_rejected_push_receives_authoritative_copy(self) -> None:
        """推送被拒时，服务端要在同一次响应里把自己那份发回来。"""
        desktop = self.make_client("desktop")
        phone = self.make_client("phone")

        task = desktop.tasks.create(TaskDraft(text="服务端版本"))
        desktop.sync.sync_now()
        phone.sync.sync_now()

        # 手机拿一个更旧的时间戳去推，一定会被拒
        stale = phone.tasks.get(task.id)
        stale.text = "时钟慢了的设备改的"
        stale.updated_at = stale.updated_at - 60_000
        stale.dirty = True
        phone.tasks.save()

        phone.sync.sync_now()
        self.assertEqual(phone.tasks.get(task.id).text, "服务端版本")
        self.assertEqual(phone.tasks.dirty_records(), [])

    def test_far_future_timestamp_is_clamped(self) -> None:
        """时钟错乱的设备不能写出一条谁都改不动的待办。"""
        desktop = self.make_client("desktop")
        poisoned = {
            "id": "1754000000000-poison",
            "text": "来自未来",
            "status": "todo",
            "deleted": False,
            "updated_at": now_ms() + 365 * _MS_PER_DAY,
        }
        SyncClient(self.base_url).sync(self.sync_code, 0, [poisoned])

        desktop.sync.sync_now()
        task = desktop.tasks.get(poisoned["id"])
        self.assertIsNotNone(task)
        # 时间戳被按服务端时钟封顶，之后正常的编辑才推得上去
        self.assertLess(task.updated_at, now_ms() + 10 * 60 * 1000)

        desktop.tasks.update(task.id, text="改回来")
        desktop.sync.sync_now()
        self.assertEqual(desktop.tasks.dirty_records(), [])

        fresh = self.make_client("fresh")
        fresh.sync.sync_now()
        self.assertEqual(fresh.tasks.get(poisoned["id"]).text, "改回来")

    def test_different_sync_codes_are_isolated(self) -> None:
        mine = self.make_client("mine")
        other = self.make_client("other", sync_code=generate_sync_code())

        mine.tasks.create(TaskDraft(text="我的私事"))
        mine.sync.sync_now()
        other.sync.sync_now()

        self.assertEqual(other.tasks.tasks, [])

    def test_project_tasks_sync(self) -> None:
        desktop = self.make_client("desktop")
        phone = self.make_client("phone")

        desktop.tasks.create_many(
            [
                TaskDraft(text="甲", project="Q3 增长"),
                TaskDraft(text="乙", project="Q3 增长"),
            ]
        )
        desktop.sync.sync_now()
        phone.sync.sync_now()

        self.assertEqual(phone.projects.names(), ["Q3 增长"])
        self.assertEqual(phone.projects.summary("Q3 增长").total, 2)

    def test_idempotent_sync(self) -> None:
        desktop = self.make_client("desktop")
        desktop.tasks.create(TaskDraft(text="只应出现一次"))

        first = desktop.sync.sync_now()
        second = desktop.sync.sync_now()
        third = desktop.sync.sync_now()

        self.assertEqual(first.pushed, 1)
        self.assertEqual(second.pushed, 0)
        self.assertEqual(third.pushed, 0)
        self.assertEqual(len(desktop.tasks.tasks), 1)
        # 已推送过就不再是脏数据
        self.assertEqual(desktop.tasks.dirty_records(), [])

    def test_full_pull_on_fresh_device(self) -> None:
        desktop = self.make_client("desktop")
        for index in range(5):
            desktop.tasks.create(TaskDraft(text=f"事项{index}"))
        desktop.sync.sync_now()

        # 新设备游标为 0，应拿到全量
        fresh = self.make_client("fresh_phone")
        result = fresh.sync.sync_now()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(fresh.tasks.tasks), 5)
        self.assertGreater(fresh.config.sync.cursor, 0)


class SyncFailureTest(SyncTestBase):
    """异常路径。"""

    def test_unconfigured_sync_is_noop(self) -> None:
        backend = self.make_client("desktop")
        backend.config.sync.enabled = False
        result = backend.sync.sync_now()
        self.assertFalse(result.ok)
        self.assertIn("尚未配置", result.error)

    def test_unreachable_server_records_error(self) -> None:
        backend = self.make_client("desktop")
        # 指向一个几乎不可能有服务在听的端口
        backend.config.sync.server_url = "http://127.0.0.1:1"
        backend.tasks.create(TaskDraft(text="离线也不能丢"))

        result = backend.sync.sync_now()
        self.assertFalse(result.ok)
        self.assertTrue(backend.config.sync.last_error)
        # 本地数据必须完好，且仍标记为待推送
        self.assertEqual([task.text for task in backend.tasks.tasks], ["离线也不能丢"])
        self.assertEqual(len(backend.tasks.dirty_records()), 1)

    def test_edit_during_push_is_not_lost(self) -> None:
        """推送期间又改了同一条待办时，脏标记必须保留。"""
        backend = self.make_client("desktop")
        task = backend.tasks.create(TaskDraft(text="第一版"))

        batch = backend.sync.prepare()
        # 模拟网络往返期间用户又改了一次
        backend.tasks.update(task.id, text="第二版")
        response = backend.sync.exchange(batch)
        backend.sync.apply(batch, response)

        self.assertEqual(len(backend.tasks.dirty_records()), 1)
        follow_up = backend.sync.sync_now()
        self.assertTrue(follow_up.ok, follow_up.error)
        self.assertEqual(backend.tasks.dirty_records(), [])
        self.assertEqual(backend.tasks.get(task.id).text, "第二版")

    def test_cursor_does_not_advance_when_save_fails(self) -> None:
        """待办没能落盘时游标必须原地不动，否则这批改动再也不会下发。"""
        source = self.make_client("source")
        source.tasks.create(TaskDraft(text="必须送达"))
        source.sync.sync_now()

        target = self.make_client("target")
        before = target.config.sync.cursor
        batch = target.sync.prepare()
        response = target.sync.exchange(batch)

        # 让落盘失败，模拟磁盘满/目录只读
        target.tasks.save = lambda notify=True: False
        result = target.sync.apply(batch, response)

        self.assertFalse(result.ok)
        self.assertEqual(target.config.sync.cursor, before)
        self.assertTrue(target.config.sync.last_error)

    def test_quota_refusal_keeps_dirty_flag(self) -> None:
        """服务端存不下的记录不能当成推送成功，否则它就只剩本机有了。"""
        backend = self.make_client("desktop")
        task = backend.tasks.create(TaskDraft(text="超额待办"))

        batch = backend.sync.prepare()
        # 手工构造一个「容量已满」的响应
        response = {
            "cursor": batch.since,
            "changes": [],
            "accepted": [],
            "rejected": [],
            "refused": [task.id],
            "more": False,
            "server_time": now_ms(),
        }
        result = backend.sync.apply(batch, response)

        self.assertFalse(result.ok)
        self.assertIn("存储已满", result.error)
        self.assertEqual([item.id for item in backend.tasks.dirty_records()], [task.id])

    def test_refused_records_do_not_spin_the_round_loop(self) -> None:
        """被拒收的记录会一直是脏的，但不能让每次同步都空转满 MAX_ROUNDS 轮。"""
        backend = self.make_client("desktop")
        task = backend.tasks.create(TaskDraft(text="超额待办"))
        batch = backend.sync.prepare()
        response = {
            "cursor": batch.since,
            "changes": [],
            "accepted": [],
            "rejected": [],
            "refused": [task.id],
            "more": False,
            "server_time": now_ms(),
        }
        self.assertFalse(backend.sync.apply(batch, response).more)


class MobileProtocolTest(SyncTestBase):
    """手机端（web/app.js）与桌面端的协议兼容性。

    手机端只管理一部分字段，构造的待办对象比桌面端精简；这里直接按 app.js
    的报文格式发请求，验证两端能互相理解，且手机端的编辑不会抹掉
    桌面端独有的设置（循环、小步骤、强提醒）。
    """

    def _mobile_sync(self, changes, since=0):
        """模拟手机端发一次同步请求。"""
        return SyncClient(self.base_url).sync(self.sync_code, since, changes)

    def test_mobile_created_task_reaches_desktop(self) -> None:
        # app.js 里 addTask() 构造的对象形状
        mobile_task = {
            "id": "1754000000000-abc123",
            "text": "手机上加的",
            "status": "todo",
            "category": "生活",
            "due": "2026-08-05 09:00",
            "priority": "P1",
            "note": "",
            "project": "",
            "pinned": False,
            "created": "2026-08-01T09:00:00",
            "deleted": False,
            "updated_at": now_ms(),
        }
        self._mobile_sync([mobile_task])

        desktop = self.make_client("desktop")
        desktop.sync.sync_now()

        task = desktop.tasks.get(mobile_task["id"])
        self.assertIsNotNone(task)
        self.assertEqual(task.text, "手机上加的")
        self.assertEqual(task.priority, "P1")
        # 手机没传的字段由桌面端补成默认值
        self.assertEqual(task.recur, "不循环")
        self.assertEqual(task.remind, "到期当天")
        self.assertFalse(task.strong.enabled)
        self.assertEqual(task.subtasks, [])

    def test_mobile_edit_preserves_desktop_only_fields(self) -> None:
        desktop = self.make_client("desktop")
        task = desktop.tasks.create(
            TaskDraft(text="每周复盘", due="2026-08-07", recur="每周", remind="提前1天")
        )
        desktop.tasks.replace_subtasks(task.id, [SubTask("拉数据"), SubTask("写结论")])
        desktop.sync.sync_now()

        # 手机端拉取，拿到完整对象
        pulled = self._mobile_sync([])
        self.assertEqual(len(pulled["changes"]), 1)
        mobile_copy = pulled["changes"][0]
        self.assertEqual(mobile_copy["recur"], "每周")
        self.assertEqual(len(mobile_copy["subtasks"]), 2)

        # 手机端只改自己管的字段（app.js saveEditor 的做法）
        mobile_copy["text"] = "每周复盘（手机改）"
        mobile_copy["priority"] = "P0"
        mobile_copy["updated_at"] = now_ms()
        mobile_copy.pop("dirty", None)
        self._mobile_sync([mobile_copy], since=pulled["cursor"])

        desktop.sync.sync_now()
        updated = desktop.tasks.get(task.id)
        self.assertEqual(updated.text, "每周复盘（手机改）")
        self.assertEqual(updated.priority, "P0")
        # 桌面端独有的设置必须完好
        self.assertEqual(updated.recur, "每周")
        self.assertEqual(updated.remind, "提前1天")
        self.assertEqual([item.text for item in updated.subtasks], ["拉数据", "写结论"])

    def test_mobile_delete_reaches_desktop(self) -> None:
        desktop = self.make_client("desktop")
        task = desktop.tasks.create(TaskDraft(text="待删除"))
        desktop.sync.sync_now()

        pulled = self._mobile_sync([])
        mobile_copy = pulled["changes"][0]
        mobile_copy["deleted"] = True
        mobile_copy["updated_at"] = now_ms()
        self._mobile_sync([mobile_copy], since=pulled["cursor"])

        desktop.sync.sync_now()
        self.assertIsNone(desktop.tasks.get(task.id))
        self.assertEqual(desktop.tasks.tasks, [])


class TombstoneTest(SyncTestBase):
    """墓碑清理。"""

    def test_old_synced_tombstone_is_purged_on_reload(self) -> None:
        backend = self.make_client("desktop")
        task = backend.tasks.create(TaskDraft(text="很久以前删的"))
        backend.sync.sync_now()
        backend.tasks.delete(task.id)
        backend.sync.sync_now()

        # 把墓碑时间改成很久以前，再重新载入
        record = backend.tasks.all_records()[0]
        record.updated_at = now_ms() - (TOMBSTONE_KEEP_DAYS + 5) * _MS_PER_DAY
        backend.tasks.save()
        backend.tasks.reload()

        self.assertEqual(backend.tasks.all_records(), [])

    def test_unsynced_tombstone_is_kept(self) -> None:
        backend = self.make_client("desktop")
        task = backend.tasks.create(TaskDraft(text="还没同步就删了"))
        backend.tasks.delete(task.id)

        record = backend.tasks.all_records()[0]
        record.updated_at = now_ms() - (TOMBSTONE_KEEP_DAYS + 5) * _MS_PER_DAY
        backend.tasks.save()
        backend.tasks.reload()

        # 尚未推送过的墓碑不能丢，否则删除动作传不到其他设备
        self.assertEqual(len(backend.tasks.all_records()), 1)


if __name__ == "__main__":
    unittest.main()
