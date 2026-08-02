/**
 * 西瓜todo 手机端。
 *
 * 与桌面端共用同一套同步协议和数据结构：
 * - 待办对象的字段与桌面端 Task.to_dict() 一致；
 * - 本端不认识的字段（循环、小步骤、强提醒等）**原样保留**，
 *   编辑时只覆盖自己改动的键，避免把桌面端的设置抹掉；
 * - 删除是软删除（deleted 墓碑），否则另一端会把它同步回来。
 */
(function () {
  "use strict";

  // ------------------------------------------------------------ 常量
  var STORAGE_KEY = "watermelon_todo_v3";
  var SETTINGS_KEY = "watermelon_sync_v3";
  var FALLBACK_SERVER = "http://47.120.58.231:52121";
  var SYNC_INTERVAL_MS = 60000;
  var DEBOUNCE_MS = 2500;
  var MAX_ROUNDS = 20;
  // 墓碑本地保留天数，与桌面端一致（要短于服务端的 60 天）
  var TOMBSTONE_KEEP_MS = 45 * 24 * 3600 * 1000;

  var PRIORITIES = ["P0", "P1", "P2", "重要", "普通"];
  var PRIORITY_COLORS = {
    P0: "#D92D20", P1: "#F2564B", P2: "#F58C4B", 重要: "#F5A623", 普通: "#98A2B3"
  };
  var CATEGORIES = ["工作", "生活", "学习", "其他"];
  var DAILY_SCOPE = "";

  var CHEERS = [
    "加油啦！✨", "今天也要元气满满哦~ 🌸", "一件一件来，你可以的！💪",
    "慢慢来，会更快 🍀", "完成的每一件都值得鼓励 🎉", "别忘了对自己好一点 ☕",
    "前进一小步也是胜利 🚀", "你比想象中更棒 💖", "把大事拆小，就不难啦 📌"
  ];

  // ------------------------------------------------------------ 状态
  var tasks = [];
  var settings = {
    userId: "",
    serverUrl: "",
    accessToken: "",
    cursor: 0,
    lastSyncAt: 0,
    enabled: true
  };
  var scope = DAILY_SCOPE;      // "" 表示日常待办，否则为项目名
  var editingId = null;
  var syncing = false;
  var debounceTimer = null;

  var $ = function (selector) { return document.querySelector(selector); };

  // ------------------------------------------------------------ 工具
  function nowMs() { return Date.now(); }

  /** 与桌面端同款 ID：毫秒时间戳 + 随机后缀，多端离线新建也不会撞。 */
  function newId() {
    var random = Math.random().toString(16).slice(2, 8);
    return String(nowMs()) + "-" + random;
  }

  /** 本地时间的 ISO 字符串（秒级），与桌面端 created 字段格式一致。 */
  function localIso() {
    var d = new Date();
    var pad = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      "T" + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
  }

  function load() {
    try {
      tasks = JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    } catch (error) {
      console.warn("本地待办数据损坏，按空数据处理", error);
      tasks = [];
    }
    try {
      var saved = JSON.parse(localStorage.getItem(SETTINGS_KEY));
      if (saved) { Object.assign(settings, saved); }
    } catch (error) {
      console.warn("同步设置损坏，恢复默认", error);
    }
    if (!settings.serverUrl) { settings.serverUrl = defaultServer(); }
    purgeStaleTombstones();
  }

  /**
   * 清掉早已推送过的老墓碑，和桌面端一个规则。
   *
   * 不清的话删除记录会在 localStorage 里无限堆积，而手机的配额只有几 MB，
   * 写满之后新数据就存不下了。还没推送过的墓碑一定要留着，
   * 否则这台设备上的删除永远传不出去。
   */
  function purgeStaleTombstones() {
    var deadline = nowMs() - TOMBSTONE_KEEP_MS;
    var kept = tasks.filter(function (task) {
      return !(task.deleted && !task.dirty && (task.updated_at || 0) < deadline);
    });
    if (kept.length !== tasks.length) {
      tasks = kept;
      save();
    }
  }

  /**
   * 写入本地待办。
   *
   * 返回是否写成功：配额写满（以及 iOS 无痕模式）时 setItem 会抛异常，
   * 调用方必须据此决定要不要继续往下走。
   */
  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
      return true;
    } catch (error) {
      console.error("本地存储写入失败", error);
      toast("本地存储空间不足，请清理后重试");
      return false;
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
      return true;
    } catch (error) {
      console.error("同步设置写入失败", error);
      return false;
    }
  }

  /**
   * 默认接口地址。
   *
   * 页面由同步服务自己发出时用同源地址——这样在裸 HTTP 下也不会触发
   * 「HTTPS 页面请求 HTTP 接口」的混合内容拦截，也不需要 CORS。
   */
  function defaultServer() {
    if (location.protocol === "http:" || location.protocol === "https:") {
      return location.origin;
    }
    return FALLBACK_SERVER;
  }

  function toast(message) {
    var element = $("#toast");
    element.textContent = message;
    element.classList.add("show");
    clearTimeout(element._timer);
    element._timer = setTimeout(function () {
      element.classList.remove("show");
    }, 1800);
  }

  /**
   * 标记本地改动：更新时间戳 + 置脏，等待下次同步推送。
   *
   * 时间戳保证严格递增：毫秒精度下连点两次很可能落在同一毫秒，
   * 而服务端按「不比我新就拒绝」判定，时间戳不推进的话第二次改动会被丢掉。
   */
  function touch(task) {
    task.updated_at = Math.max(nowMs(), (task.updated_at || 0) + 1);
    task.dirty = true;
  }

  function visibleTasks() {
    return tasks.filter(function (task) {
      return !task.deleted && (task.project || "") === scope;
    });
  }

  function projectNames() {
    var seen = [];
    tasks.forEach(function (task) {
      var name = task.project || "";
      if (name && !task.deleted && seen.indexOf(name) < 0) { seen.push(name); }
    });
    return seen;
  }

  // ------------------------------------------------------------ 截止时间
  function parseDue(due) {
    if (!due) { return null; }
    var text = String(due).trim().replace(" ", "T");
    var parsed = new Date(text);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  function dueLabel(task) {
    var parsed = parseDue(task.due);
    if (!parsed) { return null; }
    var pad = function (n) { return String(n).padStart(2, "0"); };
    var hasTime = String(task.due).indexOf(":") > 0;
    var clock = hasTime ? " " + pad(parsed.getHours()) + ":" + pad(parsed.getMinutes()) : "";
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    var target = new Date(parsed);
    target.setHours(0, 0, 0, 0);
    var days = Math.round((target - today) / 86400000);

    if (task.status === "done") {
      return { text: pad(parsed.getMonth() + 1) + "-" + pad(parsed.getDate()) + clock, overdue: false };
    }
    if (days < 0) { return { text: "已过期 " + -days + " 天", overdue: true }; }
    if (days === 0) { return { text: "今天" + clock, overdue: true }; }
    if (days === 1) { return { text: "明天" + clock, overdue: false }; }
    if (days <= 7) { return { text: days + " 天后" + clock, overdue: false }; }
    return { text: pad(parsed.getMonth() + 1) + "-" + pad(parsed.getDate()) + clock, overdue: false };
  }

  /** 排序：未完成在前 → 置顶在前 → 优先级 → 截止时间。 */
  function sortTasks(list) {
    var rank = function (task) { return PRIORITIES.indexOf(task.priority || "普通"); };
    var dueValue = function (task) {
      var parsed = parseDue(task.due);
      if (parsed) { return parsed.getTime(); }
      var end = new Date();
      end.setHours(23, 59, 0, 0);
      return end.getTime();
    };
    return list.slice().sort(function (a, b) {
      var doneDiff = (a.status === "done" ? 1 : 0) - (b.status === "done" ? 1 : 0);
      if (doneDiff) { return doneDiff; }
      var pinDiff = (a.pinned ? 0 : 1) - (b.pinned ? 0 : 1);
      if (pinDiff) { return pinDiff; }
      var priorityDiff = rank(a) - rank(b);
      if (priorityDiff) { return priorityDiff; }
      return dueValue(a) - dueValue(b);
    });
  }

  // ------------------------------------------------------------ 渲染
  function render() {
    renderScopes();
    var list = sortTasks(visibleTasks());
    var listElement = $("#list");
    listElement.innerHTML = "";

    var total = list.length;
    var done = list.filter(function (task) { return task.status === "done"; }).length;
    $("#statTotal").textContent = total;
    $("#statDone").textContent = done;
    $("#statLeft").textContent = total - done;
    $("#progress").style.width = total ? (done / total * 100) + "%" : "0";
    $("#empty").style.display = total ? "none" : "block";

    list.forEach(function (task) {
      listElement.appendChild(renderTask(task));
    });
    renderSyncStatus();
  }

  function renderScopes() {
    var bar = $("#scopes");
    bar.innerHTML = "";
    var scopes = [{ key: DAILY_SCOPE, label: "📋 日常" }];
    projectNames().forEach(function (name) {
      scopes.push({ key: name, label: "📁 " + name });
    });
    scopes.forEach(function (item) {
      var chip = document.createElement("button");
      chip.className = "chip" + (item.key === scope ? " active" : "");
      chip.textContent = item.label;
      chip.onclick = function () {
        scope = item.key;
        render();
      };
      bar.appendChild(chip);
    });
  }

  function renderTask(task) {
    var item = document.createElement("li");
    item.className = "task" + (task.status === "done" ? " done" : "");

    var row = document.createElement("div");
    row.className = "trow";

    var check = document.createElement("div");
    check.className = "check";
    check.textContent = task.status === "done" ? "✓" : "";
    check.onclick = function () { toggleTask(task.id); };
    row.appendChild(check);

    var body = document.createElement("div");
    body.className = "tbody";

    var title = document.createElement("div");
    title.className = "title";
    title.textContent = (task.pinned ? "📌 " : "") + task.text;
    title.onclick = function () { openEditor(task.id); };
    body.appendChild(title);

    var meta = document.createElement("div");
    meta.className = "meta";
    if (task.priority && task.priority !== "普通") {
      var priority = document.createElement("span");
      priority.className = "badge";
      priority.style.background = PRIORITY_COLORS[task.priority] || "#98A2B3";
      priority.style.color = "#fff";
      priority.textContent = task.priority;
      meta.appendChild(priority);
    }
    if (task.category) {
      var category = document.createElement("span");
      category.className = "badge light";
      category.textContent = task.category;
      meta.appendChild(category);
    }
    var due = dueLabel(task);
    if (due) {
      var dueElement = document.createElement("span");
      dueElement.className = "badge" + (due.overdue ? " over" : " light");
      dueElement.textContent = "⏰ " + due.text;
      meta.appendChild(dueElement);
    }
    if (task.note) {
      var note = document.createElement("span");
      note.className = "badge light";
      note.textContent = "📝";
      meta.appendChild(note);
    }
    // 桌面端专属能力：这里只做提示，不提供编辑，同步时原样保留
    if (task.recur && task.recur !== "不循环") {
      var recur = document.createElement("span");
      recur.className = "badge light";
      recur.textContent = "🔁 " + task.recur;
      meta.appendChild(recur);
    }
    if (task.subtasks && task.subtasks.length) {
      var subDone = task.subtasks.filter(function (s) { return s.done; }).length;
      var sub = document.createElement("span");
      sub.className = "badge light";
      sub.textContent = "☑ " + subDone + "/" + task.subtasks.length;
      meta.appendChild(sub);
    }
    body.appendChild(meta);
    row.appendChild(body);

    var remove = document.createElement("div");
    remove.className = "del";
    remove.textContent = "✕";
    remove.onclick = function () { deleteTask(task.id); };
    row.appendChild(remove);

    item.appendChild(row);
    return item;
  }

  function renderSyncStatus() {
    var label = $("#syncStatus");
    if (!settings.userId) {
      label.textContent = "未开启同步";
      return;
    }
    if (syncing) {
      label.textContent = "同步中…";
      return;
    }
    if (!settings.lastSyncAt) {
      label.textContent = "已配置，等待同步";
      return;
    }
    var moment = new Date(settings.lastSyncAt);
    var pad = function (n) { return String(n).padStart(2, "0"); };
    label.textContent = "上次同步 " + pad(moment.getMonth() + 1) + "-" +
      pad(moment.getDate()) + " " + pad(moment.getHours()) + ":" + pad(moment.getMinutes());
  }

  // ------------------------------------------------------------ 增删改
  function addTask() {
    var input = $("#taskInput");
    var text = input.value.trim();
    if (!text) { input.focus(); return; }

    var task = {
      id: newId(),
      text: text,
      status: "todo",
      category: $("#categoryPick").value || "其他",
      due: $("#duePick").value ? $("#duePick").value.replace("T", " ") : "",
      priority: $("#priorityPick").value || "普通",
      note: "",
      project: scope,
      pinned: false,
      created: localIso(),
      deleted: false
    };
    touch(task);
    tasks.push(task);
    // save() 失败时它自己会提示存储写满，别再用成功文案盖掉；
    // 同步照常安排——把数据推到服务端反而是此时最靠谱的保命手段
    var stored = save();
    input.value = "";
    $("#duePick").value = "";
    render();
    if (stored) { toast("已添加 🍉"); }
    scheduleSync();
  }

  function findTask(id) {
    for (var i = 0; i < tasks.length; i += 1) {
      if (tasks[i].id === id) { return tasks[i]; }
    }
    return null;
  }

  function toggleTask(id) {
    var task = findTask(id);
    if (!task) { return; }
    task.status = task.status === "done" ? "todo" : "done";
    touch(task);
    var stored = save();
    render();
    if (stored && task.status === "done") {
      toast(CHEERS[Math.floor(Math.random() * CHEERS.length)]);
    }
    scheduleSync();
  }

  function deleteTask(id) {
    var task = findTask(id);
    if (!task) { return; }
    // 软删除：留下墓碑，另一台设备才知道这条被删了
    task.deleted = true;
    touch(task);
    save();
    render();
    scheduleSync();
  }

  function openEditor(id) {
    var task = findTask(id);
    if (!task) { return; }
    editingId = id;
    $("#editText").value = task.text;
    $("#editNote").value = task.note || "";
    $("#editDue").value = task.due ? String(task.due).replace(" ", "T") : "";
    $("#editPriority").value = task.priority || "普通";
    $("#editCategory").value = task.category || "其他";
    $("#editPin").checked = !!task.pinned;
    openSheet("#editSheet");
  }

  function saveEditor() {
    var task = findTask(editingId);
    if (!task) { closeSheet("#editSheet"); return; }
    var text = $("#editText").value.trim();
    if (!text) { toast("内容不能为空"); return; }

    // 只覆盖本端管理的字段，其余（循环/小步骤/强提醒）保持原样
    task.text = text;
    task.note = $("#editNote").value.trim();
    task.due = $("#editDue").value ? $("#editDue").value.replace("T", " ") : "";
    task.priority = $("#editPriority").value;
    task.category = $("#editCategory").value;
    task.pinned = $("#editPin").checked;
    touch(task);
    var stored = save();
    closeSheet("#editSheet");
    render();
    if (stored) { toast("已保存"); }
    scheduleSync();
  }

  // ------------------------------------------------------------ 同步
  function apiUrl(path) {
    var base = (settings.serverUrl || defaultServer()).replace(/\/+$/, "");
    return base + path;
  }

  function scheduleSync() {
    if (!settings.userId || !settings.enabled) { return; }
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { syncNow(false); }, DEBOUNCE_MS);
  }

  /**
   * 与服务端交换一次数据。
   * @param {boolean} manual 是否用户手动触发（决定是否弹提示）
   * @param {number} round   当前轮次，服务端分页时会递归续跑
   */
  function syncNow(manual, round) {
    round = round || 0;
    if (!settings.userId) {
      if (manual) { toast("请先填写同步码"); }
      return Promise.resolve();
    }
    if (syncing && round === 0) { return Promise.resolve(); }
    if (round >= MAX_ROUNDS) {
      // 必须复位 syncing：上面那道 round === 0 的闸门会因此一直关着，
      // 定时同步和切回前台同步会在本页面剩余的生命周期里全部失效
      syncing = false;
      renderSyncStatus();
      if (manual) { toast("数据较多，已同步一部分，稍后继续"); }
      return Promise.resolve();
    }

    syncing = true;
    renderSyncStatus();

    var dirty = tasks.filter(function (task) { return task.dirty; });
    var stamps = {};
    var changes = dirty.map(function (task) {
      stamps[task.id] = task.updated_at;
      var copy = Object.assign({}, task);
      delete copy.dirty;   // dirty 只描述本机状态，不该传给其他设备
      return copy;
    });

    var headers = { "Content-Type": "application/json" };
    if (settings.accessToken) { headers["X-Access-Token"] = settings.accessToken; }

    return fetch(apiUrl("/api/sync"), {
      method: "POST",
      headers: headers,
      body: JSON.stringify({
        user_id: settings.userId,
        since: settings.cursor || 0,
        changes: changes
      })
    }).then(function (response) {
      if (!response.ok) { throw new Error("服务端返回 " + response.status); }
      return response.json();
    }).then(function (payload) {
      // rejected：服务端已有同样或更新的版本，这条推送就此作罢。
      // refused：服务端根本没存下（容量满了），必须保留脏标记等下次重试，
      //   当成推送成功的话这条待办就只剩这台手机上有了。
      var refused = payload.refused || [];
      var settled = (payload.accepted || []).concat(payload.rejected || [])
        .filter(function (id) { return refused.indexOf(id) < 0; });
      settled.forEach(function (id) {
        var task = findTask(id);
        // 请求期间又改过就保留脏标记，等下一轮再推
        if (task && task.updated_at === stamps[id]) { task.dirty = false; }
      });

      var applied = mergeRemote(payload.changes || []);
      // 先把待办落盘，成功了才允许游标前进。反过来的话，配额写满时游标已经
      // 越过这批改动，而拉取条件是 server_seq > cursor，它们再也不会下发
      if (!save()) {
        syncing = false;
        renderSyncStatus();
        return null;
      }
      settings.cursor = payload.cursor || settings.cursor;
      settings.lastSyncAt = nowMs();
      saveSettings();

      var stillDirty = tasks.some(function (task) {
        return task.dirty && refused.indexOf(task.id) < 0;
      });
      if (payload.more || stillDirty) {
        return syncNow(manual, round + 1);
      }
      syncing = false;
      render();
      if (refused.length) {
        toast("服务端存储已满，" + refused.length + " 条未能上传");
      } else if (manual) {
        toast(applied ? "同步完成，更新 " + applied + " 条" : "已是最新");
      } else if (applied) {
        toast("同步到 " + applied + " 条更新");
      }
      return null;
    }).catch(function (error) {
      syncing = false;
      renderSyncStatus();
      console.warn("同步失败", error);
      if (manual) { toast("同步失败：" + error.message); }
      return null;
    });
  }

  /**
   * 合并服务端下发的记录：updated_at 更大的一方胜出。
   *
   * 打平时以远端为准，必须和服务端的判定方向一致（服务端在相等时拒绝上传、
   * 保留自己那份）。两边都偏袒自己的话，同一毫秒内改同一条待办的两台设备
   * 会各执己见、永久分叉，而且谁都不会察觉。
   */
  function mergeRemote(incoming) {
    var applied = 0;
    incoming.forEach(function (remote) {
      if (!remote || !remote.id) { return; }
      var local = findTask(remote.id);
      if (!local) {
        remote.dirty = false;
        tasks.push(remote);
        applied += 1;
        return;
      }
      if ((remote.updated_at || 0) < (local.updated_at || 0)) { return; }
      if ((remote.updated_at || 0) === (local.updated_at || 0) && sameTask(remote, local)) {
        return;   // 服务端回发的就是本机刚推上去的那份，不必当成变化去刷界面
      }
      remote.dirty = false;
      tasks[tasks.indexOf(local)] = remote;
      applied += 1;
    });
    return applied;
  }

  /** 两条待办除 dirty（纯本机状态）之外是否完全一致。 */
  function sameTask(left, right) {
    var strip = function (task) {
      var copy = Object.assign({}, task);
      delete copy.dirty;
      return JSON.stringify(Object.keys(copy).sort().map(function (key) {
        return [key, copy[key]];
      }));
    };
    return strip(left) === strip(right);
  }

  function randomCode() {
    var alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    var buffer = new Uint8Array(22);
    (window.crypto || window.msCrypto).getRandomValues(buffer);
    var code = "";
    for (var i = 0; i < buffer.length; i += 1) {
      code += alphabet[buffer[i] % alphabet.length];
    }
    return code;
  }

  // ------------------------------------------------------------ 面板
  function openSheet(selector) { $(selector).classList.add("open"); }
  function closeSheet(selector) { $(selector).classList.remove("open"); }

  function openSyncSheet() {
    $("#syncCode").value = settings.userId || "";
    $("#syncServer").value = settings.serverUrl || defaultServer();
    $("#syncToken").value = settings.accessToken || "";
    $("#syncHint").textContent = settings.userId
      ? "在其他设备填同一个同步码即可合并数据"
      : "点「生成」得到一个随机同步码";
    openSheet("#syncSheet");
  }

  function saveSyncSettings() {
    var code = $("#syncCode").value.trim();
    var server = $("#syncServer").value.trim();
    if (code && !/^[A-Za-z0-9_\-]{6,64}$/.test(code)) {
      $("#syncHint").textContent = "同步码需为 6-64 位字母/数字/-/_";
      return;
    }
    if (code !== settings.userId) {
      settings.cursor = 0;   // 换同步码等于换数据源，游标必须归零
    }
    settings.userId = code;
    settings.serverUrl = server || defaultServer();
    settings.accessToken = $("#syncToken").value.trim();
    settings.enabled = !!code;
    saveSettings();
    closeSheet("#syncSheet");
    render();
    if (code) { syncNow(true); } else { toast("已关闭同步"); }
  }

  function copyCode() {
    var code = $("#syncCode").value.trim();
    if (!code) { $("#syncHint").textContent = "同步码是空的"; return; }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(code).then(function () {
        $("#syncHint").textContent = "已复制，去另一台设备粘贴";
      }).catch(function () {
        $("#syncHint").textContent = "复制失败，请手动长按选中";
      });
      return;
    }
    $("#syncCode").select();
    $("#syncHint").textContent = "请长按选中后复制";
  }

  // ------------------------------------------------------------ 启动
  function bindEvents() {
    $("#addBtn").onclick = addTask;
    $("#taskInput").addEventListener("keydown", function (event) {
      if (event.key === "Enter") { addTask(); }
    });
    $("#dueBtn").onclick = function () {
      var picker = $("#duePick");
      if (picker.showPicker) { picker.showPicker(); } else { picker.click(); }
    };
    $("#duePick").addEventListener("change", function () {
      $("#dueBtn").textContent = $("#duePick").value ? "🕒" : "📅";
    });

    $("#syncBtn").onclick = openSyncSheet;
    $("#syncSave").onclick = saveSyncSettings;
    $("#syncCancel").onclick = function () { closeSheet("#syncSheet"); };
    $("#syncGenerate").onclick = function () {
      $("#syncCode").value = randomCode();
      $("#syncHint").textContent = "已生成，记得在其他设备填同一个";
    };
    $("#syncCopy").onclick = copyCode;
    $("#syncRun").onclick = function () { closeSheet("#syncSheet"); syncNow(true); };

    $("#editSave").onclick = saveEditor;
    $("#editCancel").onclick = function () { closeSheet("#editSheet"); };
    $("#editDelete").onclick = function () {
      closeSheet("#editSheet");
      if (editingId) { deleteTask(editingId); }
    };

    // 回到前台时同步一次，手机切回来就能看到别处的改动
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { syncNow(false); }
    });
  }

  function fillSelect(selector, values) {
    var select = $(selector);
    values.forEach(function (value) {
      var option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) { return; }
    // Service Worker 要求安全上下文：裸 HTTP 下浏览器不允许注册，
    // 因此这里只在 HTTPS/localhost 时启用离线缓存。
    if (!window.isSecureContext) {
      console.info("非安全上下文，跳过 Service Worker（离线缓存不可用）");
      return;
    }
    navigator.serviceWorker.register("sw.js").then(function (registration) {
      // 主动查一次更新，并在新 Worker 接管后刷新一次，
      // 否则用户要连关两次页面才能用上新版本
      registration.update().catch(function () { return undefined; });
    }).catch(function (error) {
      console.warn("Service Worker 注册失败", error);
    });

    var reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", function () {
      if (reloading) { return; }
      reloading = true;
      location.reload();
    });
  }

  function init() {
    load();
    fillSelect("#priorityPick", PRIORITIES);
    fillSelect("#categoryPick", CATEGORIES);
    fillSelect("#editPriority", PRIORITIES);
    fillSelect("#editCategory", CATEGORIES);
    $("#categoryPick").value = "其他";
    $("#priorityPick").value = "普通";
    $("#cheer").textContent = CHEERS[Math.floor(Math.random() * CHEERS.length)];

    bindEvents();
    render();
    registerServiceWorker();

    if (settings.userId) {
      syncNow(false);
      setInterval(function () { syncNow(false); }, SYNC_INTERVAL_MS);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
