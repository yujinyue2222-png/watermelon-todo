(function () {
  "use strict";

  // ------------------------------------------------------------ 常量
  var DAILY_SCOPE = "";
  // 与桌面端 backend.core.constants.DEFAULT_CATEGORIES 完全一致
  var CATEGORIES = ["工作", "生活", "学习", "其他"];
  // 与桌面端 backend.models.enums.Priority.ORDER 完全一致
  var PRIORITIES = ["P0", "P1", "P2", "重要", "普通"];
  var PRIO_URGENT = ["P0", "P1", "P2"];
  var PRIO_COLOR = {
    "普通": "#8A94A6", "重要": "#F0A030", "P1": "#F2751F",
    "P2": "#4A90E2", "P0": "#F0405A"
  };
  var RECURS = ["不循环", "每日", "工作日", "每周", "每月", "每年"];
  var REMINDS = ["到期当天", "关闭提醒", "结束前10分钟", "结束前30分钟", "结束前2小时", "提前1天", "提前3天"];
  var STATE = { ACTIVE: 0, DOING: 1, DONE: 2 };
  var CHEERS = [
    "加油啦！✨", "今天也要元气满满哦~ 🌸", "一件一件来，你可以的！💪",
    "慢慢来，会更快 🍀", "完成的每一件都值得鼓励 🎉", "别忘了对自己好一点 ☕",
    "前进一小步也是胜利 🚀", "你比想象中更棒 💖", "把大事拆小，就不难啦 📌"
  ];
  // 内置主题（与桌面端 palettes.BUILTIN_THEMES 一致）
  var THEMES = {
    "极光白": { bg1: "#FBFCFE", bg2: "#EEF1F8", card: "#FFFFFF", accent: "#4C6FFF", accent2: "#6E8BFF", text: "#1F2733", sub: "#8A94A6", done: "#B4BCCB" },
    "奶油极光": { bg1: "#F8D6E5", bg2: "#C9F1EA", card: "#FFFDF9", accent: "#6C5CE7", accent2: "#8478EA", text: "#181716", sub: "#77716C", done: "#BDB6AF" },
    "曜石黑": { bg1: "#151A22", bg2: "#1C2129", card: "#232A34", accent: "#5B7FFF", accent2: "#7C97FF", text: "#EAEEF5", sub: "#8791A0", done: "#5A6472" },
    "薄雾蓝": { bg1: "#E3EEFB", bg2: "#CFE0F5", card: "#FFFFFF", accent: "#4A90E2", accent2: "#78B4F0", text: "#1E3A5F", sub: "#6E86A6", done: "#A7BCD6" },
    "抹茶绿": { bg1: "#F0F7F1", bg2: "#DBEBE0", card: "#FFFFFF", accent: "#2FA96B", accent2: "#4FC186", text: "#233529", sub: "#7A9083", done: "#AECBB7" },
    "落日橘": { bg1: "#FEF4EE", bg2: "#F5E2D4", card: "#FFFFFF", accent: "#F2751F", accent2: "#FB9450", text: "#3A2A22", sub: "#A88E7F", done: "#D9C2B3" },
    "暗夜紫": { bg1: "#1A1626", bg2: "#221D33", card: "#2A2440", accent: "#9B6BFF", accent2: "#B48CFF", text: "#EEE9F7", sub: "#9A90B4", done: "#6C6284" },
    "西瓜红": { bg1: "#FFF0F1", bg2: "#F6D9DD", card: "#FFFFFF", accent: "#F0405A", accent2: "#FF6E82", text: "#3A1F24", sub: "#B08890", done: "#E0B7BD" },
    "樱花粉": { bg1: "#FDEFF5", bg2: "#F6DCE8", card: "#FFFFFF", accent: "#F06AAE", accent2: "#FB93C6", text: "#3E2733", sub: "#B58AA0", done: "#E4BCD2" },
    "海洋青": { bg1: "#E9F7F6", bg2: "#CFEAE8", card: "#FFFFFF", accent: "#0FB5AE", accent2: "#3FD0C9", text: "#173234", sub: "#6E9896", done: "#A9D3D0" },
    "深邃蓝": { bg1: "#0E1726", bg2: "#152033", card: "#1B283E", accent: "#3DA9FC", accent2: "#6BC0FF", text: "#E6EDF7", sub: "#7E8DA6", done: "#4A5A75" },
    "薄荷青": { bg1: "#E8F8F4", bg2: "#CDEAE2", card: "#FFFFFF", accent: "#16BFA0", accent2: "#3FD8BC", text: "#1E3A33", sub: "#6E9A8E", done: "#A5D5CB" },
    "焦糖棕": { bg1: "#F7EFE6", bg2: "#ECDDCD", card: "#FFFFFF", accent: "#B07B4E", accent2: "#D29B6B", text: "#3A2A1E", sub: "#9C8270", done: "#D2BCA4" },
    "玫瑰金": { bg1: "#FCEEED", bg2: "#F4D9D8", card: "#FFFFFF", accent: "#E08A8E", accent2: "#F0AEB1", text: "#3E2A2C", sub: "#B08E92", done: "#E2BCBE" },
    "蜜桃汽水": { bg1: "#FFD9C2", bg2: "#BFE3FF", card: "#FFFFFF", accent: "#FF7A59", accent2: "#FFA07E", text: "#3D2A24", sub: "#A07C70", done: "#E0BFB5" },
    "晚霞": { bg1: "#FF9D8B", bg2: "#8E7AE6", card: "#FFFFFF", accent: "#F25C7A", accent2: "#FF8AA5", text: "#3A2433", sub: "#9E7892", done: "#E0BBC6" },
    "极光夜": { bg1: "#08182A", bg2: "#2C154A", card: "#172238", accent: "#3FE0C0", accent2: "#6BE8D0", text: "#E6EEF8", sub: "#7E8DA6", done: "#4A5A75" },
    "棉花糖": { bg1: "#FFD1E8", bg2: "#EADDFF", card: "#FFFFFF", accent: "#C56AC0", accent2: "#E094DC", text: "#3A2740", sub: "#A988A0", done: "#DDBED2" },
    "莫兰迪晨雾": { bg1: "#D8CFC2", bg2: "#A8B5AE", card: "#FFFFFF", accent: "#B08968", accent2: "#C9A384", text: "#3A352F", sub: "#8C857B", done: "#C2BAAF" }
  };
  var THEME_ORDER = [
    "极光白", "奶油极光", "曜石黑", "薄雾蓝", "抹茶绿", "落日橘", "暗夜紫", "西瓜红",
    "樱花粉", "海洋青", "深邃蓝", "薄荷青", "焦糖棕", "玫瑰金", "蜜桃汽水", "晚霞",
    "极光夜", "棉花糖", "莫兰迪晨雾"
  ];
  var THEME_KEY = "watermelon_theme_v3";
  var DIY_KEYS = [["accent", "主色"], ["accent2", "副色"], ["card", "卡片"], ["text", "文字"], ["sub", "副文字"]];

  // ------------------------------------------------------------ 状态
  var state = { tasks: [], projects: [], categories: CATEGORIES.slice(), settings: { serverUrl: "", syncCode: "123456", lastPullAt: 0 } };
  // viewMode: "daily" | "project"（与桌面端 ViewMode 对齐；不依赖 scope 是否为空判断视图）
  var viewMode = "daily";
  var scope = DAILY_SCOPE;
  var editingId = null;
  var strongId = null;
  var syncing = false;
  var debounceTimer = null;
  var multi = false;
  var selected = {};          // id -> true
  var activeCategory = "全部";
  var currentThemeName = "西瓜红";
  var diyTheme = null;
  var PULL_DEBOUNCE_MS = 4000;

  // ------------------------------------------------------------ 工具
  function $(sel) { return document.querySelector(sel); }
  function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
  function now() { return Math.floor(Date.now() / 1000); }
  function touch(t) { t.updated_at = now(); t.dirty = true; }
  function storeKey() { return "watermelon_v3_" + scope; }
  function findTask(id) { for (var i = 0; i < state.tasks.length; i++) { if (state.tasks[i].id === id) { return state.tasks[i]; } } return null; }
  function statusOf(t) {
    if (t.status === STATE.DONE) { return STATE.DONE; }
    if (t.status === STATE.DOING) { return STATE.DOING; }
    return STATE.ACTIVE;
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function toast(msg) {
    var el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.remove("show"); }, 1800);
  }
  function defaultServer() {
    return location.hostname && location.hostname !== "localhost" && location.hostname !== "127.0.0.1"
      ? location.origin : "http://47.120.58.231:52121";
  }

  // ------------------------------------------------------------ 持久化
  function save() {
    try {
      localStorage.setItem(storeKey(), JSON.stringify({ tasks: state.tasks }));
      localStorage.setItem("watermelon_projects_v3", JSON.stringify(state.projects));
      localStorage.setItem("watermelon_categories_v3", JSON.stringify(state.categories));
      localStorage.setItem("watermelon_settings_v3", JSON.stringify(state.settings));
      return true;
    } catch (e) { return false; }
  }
  function load() {
    try { state.settings = JSON.parse(localStorage.getItem("watermelon_settings_v3")) || state.settings; } catch (e) {}
    if (!state.settings.serverUrl) { state.settings.serverUrl = defaultServer(); }
    try { state.projects = JSON.parse(localStorage.getItem("watermelon_projects_v3")) || []; } catch (e) {}
    try {
      var cats = JSON.parse(localStorage.getItem("watermelon_categories_v3"));
      if (Array.isArray(cats) && cats.length) { state.categories = cats; }
    } catch (e) {}
    loadScope();
    try {
      var themeSaved = JSON.parse(localStorage.getItem(THEME_KEY));
      if (themeSaved) { if (themeSaved.name) { currentThemeName = themeSaved.name; } if (themeSaved.diy) { diyTheme = themeSaved.diy; } }
    } catch (e) {}
  }
  function loadScope() {
    try { state.tasks = JSON.parse(localStorage.getItem(storeKey())) || []; }
    catch (e) { state.tasks = []; }
  }
  function purgeStaleTombstones() {
    var cutoff = now() - 30 * 24 * 3600;
    state.tasks = state.tasks.filter(function (t) { return !(t.deleted && (t.updated_at || 0) < cutoff); });
  }
  function scheduleSync() {
    if (debounceTimer) { clearTimeout(debounceTimer); }
    debounceTimer = setTimeout(push, PULL_DEBOUNCE_MS);
  }

  // ------------------------------------------------------------ 主题
  function saveTheme() { try { localStorage.setItem(THEME_KEY, JSON.stringify({ name: currentThemeName, diy: diyTheme })); } catch (e) {} }
  function applyTheme() {
    var theme = diyTheme || THEMES[currentThemeName] || THEMES["西瓜红"];
    var root = document.documentElement.style;
    root.setProperty("--bg1", theme.bg1); root.setProperty("--bg2", theme.bg2);
    root.setProperty("--card", theme.card); root.setProperty("--accent", theme.accent);
    root.setProperty("--accent2", theme.accent2); root.setProperty("--text", theme.text);
    root.setProperty("--sub", theme.sub); root.setProperty("--done", theme.done);
    if (diyTheme) { currentThemeName = "自定义"; }
    renderThemeGrid();
  }
  function renderThemeGrid() {
    var grid = $("#themeGrid"); if (!grid) { return; }
    grid.innerHTML = "";
    THEME_ORDER.forEach(function (name) {
      var theme = THEMES[name];
      var cell = document.createElement("div");
      cell.className = "theme-cell" + (name === currentThemeName && !diyTheme ? " active" : "");
      cell.innerHTML = '<div class="swatch" style="background:' + theme.accent + '"></div>' + name;
      cell.onclick = function () {
        currentThemeName = name; diyTheme = null; saveTheme(); applyTheme(); toast("已切换：" + name);
      };
      grid.appendChild(cell);
    });
  }
  function toHex(color) {
    if (!color) { return "#ffffff"; }
    var c = String(color).replace("#", "");
    if (c.length === 3) { c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2]; }
    if (c.length === 8) { c = c.slice(0, 6); }
    return "#" + c.slice(0, 6);
  }
  function renderDiy() {
    var box = $("#diyColors"); if (!box) { return; }
    box.innerHTML = "";
    var base = diyTheme || THEMES[currentThemeName] || THEMES["西瓜红"];
    DIY_KEYS.forEach(function (pair) {
      var key = pair[0], label = pair[1];
      var row = document.createElement("div"); row.className = "diy-row";
      var span = document.createElement("span"); span.textContent = label; span.style.flex = "1";
      var input = document.createElement("input"); input.type = "color";
      input.value = toHex(base[key] || "#ffffff"); input.id = "diy-" + key;
      row.appendChild(span); row.appendChild(input); box.appendChild(row);
    });
  }
  function applyDiy() {
    var built = {};
    DIY_KEYS.forEach(function (pair) {
      var key = pair[0]; var input = $("#diy-" + key); built[key] = input ? input.value : "#ffffff";
    });
    diyTheme = { bg1: built.card, bg2: built.accent2, card: built.card, accent: built.accent, accent2: built.accent2, text: built.text, sub: built.sub, done: built.sub };
    saveTheme(); applyTheme(); toast("已应用自定义配色");
  }

  // ------------------------------------------------------------ 小步骤
  function renderSubtasks(task) {
    var list = $("#subtaskList"); if (!list) { return; }
    list.innerHTML = "";
    var subs = (task && task.subtasks) || [];
    subs.forEach(function (sub, index) {
      var row = document.createElement("div"); row.className = "subtask" + (sub.done ? " done" : "");
      var cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = !!sub.done;
      cb.onchange = function () { sub.done = cb.checked; row.className = "subtask" + (sub.done ? " done" : ""); };
      var span = document.createElement("span"); span.textContent = sub.text;
      var del = document.createElement("div"); del.className = "sub-del"; del.textContent = "✕";
      del.onclick = function () { task.subtasks.splice(index, 1); renderSubtasks(task); };
      row.appendChild(cb); row.appendChild(span); row.appendChild(del); list.appendChild(row);
    });
  }

  // ------------------------------------------------------------ 弹窗
  function openSheet(sel) { $(sel).classList.add("open"); }
  function closeSheet(sel) { $(sel).classList.remove("open"); }

  // ------------------------------------------------------------ 渲染
  function currentTasks() {
    if (viewMode === "project" && !scope) { return []; }   // 一个项目都没有：不把日常待办误算进项目视图
    return state.tasks.filter(function (t) {
      if (t.deleted) { return false; }
      if (t.project !== scope) { return false; }
      if (multi || activeCategory !== "全部") {
        var st = statusOf(t);
        if (activeCategory === "全部") { return true; }
        if (activeCategory === "已完成" || activeCategory === "进行中" || activeCategory === "待办") {
          var map = { "进行中": STATE.DOING, "待办": STATE.ACTIVE, "已完成": STATE.DONE };
          return st === map[activeCategory];
        }
        return t.category === activeCategory && st !== STATE.DONE;
      }
      return true;
    });
  }

  function render() {
    renderStats();
    renderProjects();
    renderChips();
    renderList();
    renderBatch();
  }

  // 与桌面端 StatsService._counts_for_today 一致：仅日常待办，没填截止或截止<=今天计入
  function dueDateOf(task) {
    if (!task.due) { return null; }
    var s = String(task.due).replace(" ", "T");
    var ts = Date.parse(s);
    if (isNaN(ts)) { return null; }
    var d = new Date(ts);
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }
  function countsForToday(task, today) {
    if (task.deleted) { return false; }
    if ((task.project || "") !== DAILY_SCOPE) { return false; }   // 仅日常待办
    var dd = dueDateOf(task);
    return dd === null || dd <= today;   // 没填或截止不晚于今天
  }
  function renderStats() {
    if (viewMode === "project") {
      if (!scope) {   // 一个项目都没有：与桌面端一致显示「项目 0/0」
        $("#statsText").textContent = "项目 0/0";
        $("#statsPct").textContent = "0%";
        $("#barFg").style.width = "0%";
        return;
      }
      var pt = state.tasks.filter(function (t) { return !t.deleted && (t.project || "") === scope; });
      var pdone = pt.filter(function (t) { return statusOf(t) === STATE.DONE; }).length;
      var ppct = pt.length ? Math.round((pdone / pt.length) * 100) : 0;
      $("#statsText").textContent = scope + " " + pdone + "/" + pt.length;
      $("#statsPct").textContent = ppct + "%";
      $("#barFg").style.width = ppct + "%";
      return;
    }
    var today = new Date(); today = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    var items = state.tasks.filter(function (t) { return countsForToday(t, today); });
    var done = items.filter(function (t) { return statusOf(t) === STATE.DONE; }).length;
    var urgent = items.filter(function (t) {
      return statusOf(t) !== STATE.DONE && PRIO_URGENT.indexOf(t.priority || "普通") > -1;
    }).length;
    var pct = items.length ? Math.round((done / items.length) * 100) : 0;
    var text = "今日 " + done + "/" + items.length;
    if (urgent) { text += "   🔥紧急 " + urgent; }
    $("#statsText").textContent = text;
    $("#statsPct").textContent = pct + "%";
    $("#barFg").style.width = pct + "%";
  }

  function renderProjects() {
    var picker = $("#projectPicker");
    picker.innerHTML = "";
    var names = state.projects.map(function (p) { return p.name; });
    if (!names.length) {
      var ph = document.createElement("option"); ph.value = ""; ph.textContent = "（暂无项目，点击添加待办新建）"; picker.appendChild(ph);
      picker.value = "";
      return;
    }
    names.forEach(function (n) {
      var o = document.createElement("option"); o.value = n; o.textContent = n; picker.appendChild(o);
    });
    if (names.indexOf(scope) === -1) { scope = names[0]; }
    picker.value = scope;
  }

  function renderChips() {
    var row = $("#chipRow");
    row.innerHTML = "";
    ["全部", "待办", "进行中", "已完成"].concat(state.categories).forEach(function (cat) {
      var chip = document.createElement("div");
      chip.className = "chip" + (cat === activeCategory ? " active" : "");
      chip.textContent = cat;
      chip.onclick = function () { activeCategory = cat; render(); };
      row.appendChild(chip);
    });
  }

  function dueUrgent(t) {
    if (!t.due || statusOf(t) === STATE.DONE) { return false; }
    var ts = Date.parse(t.due.replace(" ", "T") + (t.due.indexOf(":") > -1 && t.due.slice(-1) === " " ? "" : ""));
    if (isNaN(ts)) { return false; }
    return ts < Date.now();
  }
  function dueText(t) {
    if (!t.due) { return ""; }
    var d = t.due.replace(" ", " ");
    return d.slice(0, 16);
  }

  function renderList() {
    var list = $("#list");
    list.innerHTML = "";
    var tasks = currentTasks().slice().sort(function (a, b) {
      if (!!b.pinned !== !!a.pinned) { return b.pinned ? 1 : -1; }
      var oa = a.status === STATE.DONE ? 1 : 0, ob = b.status === STATE.DONE ? 1 : 0;
      if (oa !== ob) { return oa - ob; }
      return (b.updated_at || 0) - (a.updated_at || 0);
    });
    if (!tasks.length) {
      var e = document.createElement("div"); e.className = "empty";
      if (viewMode === "project" && !scope) { e.innerHTML = "还没有项目～<br>点「⚙」添加项目，或点「＋」批量添加新建吧 🍉"; }
      else if (viewMode === "project") { e.innerHTML = "这个项目还没有待办～<br>点「＋」批量添加几条吧 🍉"; }
      else { e.innerHTML = "这里还没有待办～<br>点击上方「＋ 添加待办」开始吧 🍉"; }
      list.appendChild(e); return;
    }
    tasks.forEach(function (task) { list.appendChild(renderCard(task)); });
  }

  function renderCard(task) {
    var done = statusOf(task) === STATE.DONE;
    var card = document.createElement("div");
    card.className = "card" + (done ? " done" : "");
    card.dataset.id = task.id;

    // 优先级色条
    var pbar = document.createElement("div"); pbar.className = "pbar";
    pbar.style.background = PRIO_COLOR[task.priority || "普通"] || "#8A94A6";
    card.appendChild(pbar);

    // 状态圆点
    var st = statusOf(task);
    var dot = document.createElement("button"); dot.className = "dot" + (st === STATE.DONE ? " done" : st === STATE.DOING ? " doing" : "");
    dot.textContent = st === STATE.DONE ? "●" : st === STATE.DOING ? "◐" : "○";
    dot.onclick = function (ev) { ev.stopPropagation(); cycleStatus(task); };
    card.appendChild(dot);

    // 中间
    var mid = document.createElement("div"); mid.className = "card-middle";
    var title = document.createElement("div"); title.className = "title"; title.textContent = task.text;
    mid.appendChild(title);

    if (task.note) {
      var note = document.createElement("div"); note.className = "note-preview";
      note.textContent = "📝 " + task.note; mid.appendChild(note);
    }

    var meta = document.createElement("div"); meta.className = "meta";
    var p = task.priority || "普通";
    if (p !== "普通") { meta.appendChild(badge("prio", "●" + p)); }
    if (task.category && task.category !== "其他") { meta.appendChild(badge("cat", task.category)); }
    if (task.due) { meta.appendChild(badge(dueUrgent(task) ? "due-urgent" : "due", "⏰" + dueText(task) + (dueUrgent(task) ? "(已过期)" : ""))); }
    if (task.recur && task.recur !== "不循环") { meta.appendChild(badge("recur", "🔁" + task.recur)); }
    if (task.strong) { meta.appendChild(badge("strong", "🔔强")); }
    else if (task.remind && task.remind !== "关闭提醒") { meta.appendChild(badge("remind", "🔔" + task.remind)); }
    if (task.subtasks && task.subtasks.length) {
      var sd = task.subtasks.filter(function (s) { return s.done; }).length;
      meta.appendChild(badge("sub", "☑" + sd + "/" + task.subtasks.length));
    }
    if (meta.childNodes.length) { mid.appendChild(meta); }
    card.appendChild(mid);

    // 多选勾选框（多选模式）
    if (multi) {
      var ck = document.createElement("input"); ck.type = "checkbox"; ck.style.width = "20px"; ck.style.height = "20px";
      ck.checked = !!selected[task.id];
      ck.onclick = function (ev) { ev.stopPropagation(); toggleSelect(task.id); };
      card.appendChild(ck);
    } else {
      // 编辑 / 置顶角标
      if (task.pinned) { var pin = document.createElement("div"); pin.className = "pinmark"; pin.textContent = "📌"; card.appendChild(pin); }
      var edit = document.createElement("button"); edit.className = "edit-btn"; edit.textContent = "✏️";
      edit.onclick = function (ev) { ev.stopPropagation(); openEditor(task.id); };
      card.appendChild(edit);
    }

    // 小步骤展开
    if (task.subtasks && task.subtasks.length) {
      var panel = document.createElement("div"); panel.className = "subpanel";
      task.subtasks.forEach(function (s) {
        var si = document.createElement("div"); si.className = "subitem" + (s.done ? " done" : "");
        si.innerHTML = '<span class="box">' + (s.done ? "☑" : "▢") + "</span><span>" + escapeHtml(s.text) + "</span>";
        si.onclick = function () { s.done = !s.done; si.className = "subitem" + (s.done ? " done" : ""); si.querySelector(".box").textContent = s.done ? "☑" : "▢"; touch(task); save(); renderStats(); };
        panel.appendChild(si);
      });
      card.appendChild(panel);
      card.onclick = function () { panel.classList.toggle("show"); };
    } else {
      card.onclick = function () { openEditor(task.id); };
    }
    return card;
  }
  function badge(cls, text) { var b = document.createElement("span"); b.className = "badge " + cls; b.textContent = text; return b; }

  function cycleStatus(task) {
    var st = statusOf(task);
    if (st === STATE.ACTIVE) { task.status = STATE.DOING; }
    else if (st === STATE.DOING) { task.status = STATE.DONE; }
    else { task.status = STATE.ACTIVE; }
    touch(task); save(); render();
    if (st === STATE.DOING) { toast(CHEERS[Math.floor(Math.random() * CHEERS.length)]); }
    scheduleSync();
  }

  function renderBatch() {
    var bar = $("#batchBar");
    var n = Object.keys(selected).filter(function (k) { return selected[k]; }).length;
    if (multi && n > 0) { bar.classList.add("show"); $("#batchLbl").textContent = "已选 " + n; }
    else { bar.classList.remove("show"); }
  }

  function toggleSelect(id) { if (selected[id]) { delete selected[id]; } else { selected[id] = true; } renderBatch(); }

  // ------------------------------------------------------------ 编辑
  function fillCategoryOptions() {
    var sel = $("#editCategory"); sel.innerHTML = "";
    state.categories.forEach(function (c) { var o = document.createElement("option"); o.value = c; o.textContent = c; sel.appendChild(o); });
  }
  function openEditor(id) {
    var task = findTask(id); if (!task) { return; }
    editingId = id;
    $("#editTitle").textContent = "编辑待办";
    $("#editText").value = task.text;
    $("#editNote").value = task.note || "";
    $("#editDue").value = task.due ? String(task.due).replace(" ", "T") : "";
    $("#editPriority").value = task.priority || "普通";
    $("#editCategory").value = task.category || "其他";
    $("#editPin").checked = !!task.pinned;
    $("#editRecur").value = task.recur || "不循环";
    $("#editRemind").value = task.remind || "到期当天";
    renderSubtasks(task);
    openSheet("#editSheet");
  }
  function openNew() {
    editingId = null;
    $("#editTitle").textContent = "新建待办";
    $("#editText").value = ""; $("#editNote").value = ""; $("#editDue").value = "";
    $("#editPriority").value = "普通"; $("#editCategory").value = activeCategory === "全部" ? "其他" : activeCategory;
    $("#editPin").checked = false; $("#editRecur").value = "不循环"; $("#editRemind").value = "到期当天";
    renderSubtasks({ subtasks: [] });
    openSheet("#editSheet");
  }
  function saveEditor() {
    var text = $("#editText").value.trim();
    if (!text) { toast("内容不能为空"); return; }
    var task;
    if (editingId) { task = findTask(editingId); if (!task) { closeSheet("#editSheet"); return; } }
    else {
      task = { id: uid(), status: STATE.ACTIVE, created: now(), project: scope };
      if (!task.subtasks) { task.subtasks = []; }
      state.tasks.push(task);
    }
    task.text = text; task.note = $("#editNote").value.trim();
    task.due = $("#editDue").value ? $("#editDue").value.replace("T", " ") : "";
    task.priority = $("#editPriority").value; task.category = $("#editCategory").value;
    task.pinned = $("#editPin").checked; task.recur = $("#editRecur").value; task.remind = $("#editRemind").value;
    touch(task); save(); closeSheet("#editSheet"); render(); toast("已保存"); scheduleSync();
  }
  function deleteTask(id) {
    var t = findTask(id); if (!t) { return; }
    t.deleted = true; t.status = STATE.DONE; touch(t); save(); render(); scheduleSync(); toast("已删除");
  }

  // ------------------------------------------------------------ 强提醒（字段对齐桌面端 StrongRemind）
  function openStrong(id) {
    var t = findTask(id); if (!t) { return; }
    strongId = id;
    var s = t.strong || {};
    $("#strongBeforeVal").value = s.before_value != null ? s.before_value : 0;
    $("#strongBeforeUnit").value = s.before_unit || "天";
    $("#strongIntervalVal").value = s.interval_value != null ? s.interval_value : 1;
    $("#strongIntervalUnit").value = s.interval_unit || "分钟";
    $("#strongMaxCount").value = s.max_count != null ? s.max_count : 0;
    $("#strongFloat").checked = !!s.float_window;
    openSheet("#strongSheet");
  }
  function saveStrong() {
    var t = findTask(strongId); if (!t) { closeSheet("#strongSheet"); return; }
    var enabled = $("#strongBeforeVal").value !== "0" || $("#strongFloat").checked;
    t.strong = {
      before_value: parseInt($("#strongBeforeVal").value, 10) || 0,
      before_unit: $("#strongBeforeUnit").value,
      interval_value: parseInt($("#strongIntervalVal").value, 10) || 0,
      interval_unit: $("#strongIntervalUnit").value,
      max_count: parseInt($("#strongMaxCount").value, 10) || 0,
      float_window: $("#strongFloat").checked
    };
    if (!enabled) { t.strong = null; }
    touch(t); save(); closeSheet("#strongSheet"); render();
    toast(t.strong ? "已设置强提醒" : "已关闭强提醒"); scheduleSync();
  }

  // ------------------------------------------------------------ 同步
  function buildPayload() {
    return {
      code: state.settings.syncCode,
      device: "web-" + (navigator.userAgent || "unknown").slice(0, 40),
      tasks: state.tasks,
      projects: state.projects,
      since: state.settings.lastPullAt || 0
    };
  }
  function resolveRemote(r) {
    var local = {}; state.tasks.forEach(function (t) { local[t.id] = t; });
    (r.tasks || []).forEach(function (rt) {
      var lt = local[rt.id];
      if (!lt || (rt.updated_at || 0) >= (lt.updated_at || 0)) { local[rt.id] = rt; }
    });
    state.tasks = Object.keys(local).map(function (k) { return local[k]; });
    if (r.projects) { state.projects = r.projects; }
    state.settings.lastPullAt = now();
  }
  function push() {
    if (syncing) { return; }
    var url = state.settings.serverUrl; if (!url) { return; }
    syncing = true;
    fetch(url.replace(/\/$/, "") + "/api/sync/pull", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(buildPayload())
    }).then(function (res) { return res.ok ? res.json() : null; }).then(function (data) {
      if (data && data.tasks) { resolveRemote(data); save(); render(); state.settings.lastPullAt = now(); save(); }
    }).catch(function () { /* 离线静默 */ }).then(function () { syncing = false; });
  }
  function pull() {
    if (syncing) { return; }
    var url = state.settings.serverUrl; if (!url) { return; }
    syncing = true; toast("同步中…");
    fetch(url.replace(/\/$/, "") + "/api/sync/pull", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(buildPayload())
    }).then(function (res) { return res.ok ? res.json() : null; }).then(function (data) {
      if (data && data.tasks) { resolveRemote(data); save(); render(); toast("已同步 ✅"); }
      else { toast("服务器无返回"); }
    }).catch(function () { toast("同步失败，检查服务器"); }).then(function () { syncing = false; });
  }

  // ------------------------------------------------------------ 批量/导出
  function batchAdd() {
    if (viewMode !== "project") { toast("请先切换到项目待办"); return; }
    // 无项目时与桌面端一致：先填项目名，直接创建项目
    if (!scope) {
      var projName = prompt("还没有项目。输入项目名来创建：", "");
      if (!projName || !projName.trim()) { return; }
      projName = projName.trim();
      if (!state.projects.some(function (p) { return p.name === projName; })) { state.projects.push({ name: projName }); }
      scope = projName;
    }
    var lines = prompt("每行一条待办，将添加到项目「" + scope + "」，可回车换行批量添加：");
    if (!lines) { return; }
    var added = 0;
    lines.split("\n").forEach(function (line) {
      var text = line.trim(); if (!text) { return; }
      state.tasks.push({ id: uid(), text: text, status: STATE.ACTIVE, created: now(), project: scope, subtasks: [] });
      added++;
    });
    if (added) { save(); render(); toast("已添加 " + added + " 条"); scheduleSync(); }
  }
  function exportCsv() {
    var rows = [["内容", "状态", "优先级", "分类", "截止", "循环", "提醒", "备注", "置顶", "小步骤"]];
    currentTasks().forEach(function (t) {
      rows.push([
        t.text, statusOf(t) === STATE.DONE ? "已完成" : statusOf(t) === STATE.DOING ? "进行中" : "待办",
        t.priority || "普通", t.category || "其他", t.due || "", t.recur || "不循环", t.remind || "到期当天",
        t.note || "", t.pinned ? "是" : "否",
        (t.subtasks || []).map(function (s) { return (s.done ? "[x]" : "[]") + s.text; }).join(";")
      ]);
    });
    var csv = rows.map(function (r) {
      return r.map(function (c) { return '"' + String(c).replace(/"/g, '""') + '"'; }).join(","); }
    ).join("\r\n");
    var blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = (scope || "日常") + "_待办.csv"; a.click();
    toast("已导出 CSV");
  }
  function batchDone() {
    Object.keys(selected).forEach(function (id) { if (selected[id]) { var t = findTask(id); if (t) { t.status = STATE.DONE; touch(t); } } });
    selected = {}; save(); render(); toast("已标记完成"); scheduleSync();
  }
  function batchDelete() {
    Object.keys(selected).forEach(function (id) { if (selected[id]) { var t = findTask(id); if (t) { t.deleted = true; t.status = STATE.DONE; touch(t); } } });
    selected = {}; save(); render(); toast("已删除"); scheduleSync();
  }
  function batchRecat() {
    var cat = prompt("批量改为分类（" + state.categories.join("/") + "）：", "工作");
    if (!cat) { return; }
    Object.keys(selected).forEach(function (id) { if (selected[id]) { var t = findTask(id); if (t) { t.category = cat; touch(t); } } });
    selected = {}; save(); render(); toast("已改分类"); scheduleSync();
  }

  // ------------------------------------------------------------ 事件绑定
  function bindEvents() {
    $("#cheer").onclick = function () { $("#cheer").textContent = CHEERS[Math.floor(Math.random() * CHEERS.length)]; };
    $("#tabDaily").onclick = function () { switchView("daily"); };
    $("#tabProject").onclick = function () { switchView("project"); };
    $("#addBtn").onclick = openNew;
    $("#minBtn").onclick = function () { toast("已隐藏，点首页图标即可再次打开"); window.history.length > 1 ? history.back() : close(); };

    $("#editSave").onclick = saveEditor;
    $("#editCancel").onclick = function () { closeSheet("#editSheet"); };
    $("#editDelete").onclick = function () { closeSheet("#editSheet"); if (editingId) { deleteTask(editingId); } };

    $("#subtaskAdd").onclick = function () {
      var input = $("#subtaskInput"); var text = input.value.trim(); if (!text) { input.focus(); return; }
      var task = editingId ? findTask(editingId) : { subtasks: [] };
      if (!task) { return; }
      if (!task.subtasks) { task.subtasks = []; }
      task.subtasks.push({ text: text, done: false }); input.value = ""; renderSubtasks(task);
    };
    $("#subtaskInput").addEventListener("keydown", function (e) { if (e.key === "Enter") { $("#subtaskAdd").onclick(); } });

    $("#strongSave").onclick = saveStrong; $("#strongCancel").onclick = function () { closeSheet("#strongSheet"); };
    $("#editStrong").onclick = function () { closeSheet("#editSheet"); if (editingId) { openStrong(editingId); } };

    $("#syncBtn").onclick = function () { $("#syncUrl").value = state.settings.serverUrl || ""; $("#syncCode").value = state.settings.syncCode || ""; openSheet("#syncSheet"); };
    $("#syncCancel").onclick = function () { closeSheet("#syncSheet"); };
    $("#syncNow").onclick = function () {
      state.settings.serverUrl = $("#syncUrl").value.trim(); state.settings.syncCode = $("#syncCode").value.trim() || "123456";
      save(); closeSheet("#syncSheet"); pull();
    };

    $("#menuBtn").onclick = function () { openSheet("#menuSheet"); };
    $("#menuSheet").addEventListener("click", function (e) { if (e.target === this) { closeSheet("#menuSheet"); } });
    $("#menuHide").onclick = function () { closeSheet("#menuSheet"); toast("已隐藏，点首页图标再次打开"); };
    $("#menuClearDone").onclick = function () {
      closeSheet("#menuSheet");
      if (viewMode === "project" && !scope) { toast("暂无项目"); return; }
      state.tasks.forEach(function (t) { if (!t.deleted && (t.project || "") === scope && statusOf(t) === STATE.DONE) { t.deleted = true; touch(t); } });
      save(); render(); toast("已清除已完成");
    };
    $("#menuAddCat").onclick = function () {
      closeSheet("#menuSheet");
      var name = prompt("添加分类（当前：" + state.categories.join("、") + "）：", "");
      if (!name) { return; }
      if (state.categories.indexOf(name) === -1) { state.categories.push(name); save(); fillCategoryOptions(); renderChips(); toast("已添加分类"); }
    };

    $("#themeBtn").onclick = function () { renderDiy(); openSheet("#themeSheet"); };
    $("#themeCancel").onclick = function () { closeSheet("#themeSheet"); };
    $("#diyApply").onclick = applyDiy;

    $("#projectPicker").onchange = function () {
      var name = $("#projectPicker").value;
      if (!name) { return; }   // 占位项「（暂无项目…）」不可选
      scope = name; activeCategory = "全部"; loadScope(); render();
    };
    $("#projManage").onclick = function () {
      var names = state.projects.map(function (p) { return p.name; }).join("、") || "（暂无）";
      var name = prompt("项目管理。现有：" + names + "\n输入新项目名以添加；输入已有项目名将删除：", "");
      if (!name) { return; }
      var exist = state.projects.some(function (p) { return p.name === name; });
      if (exist) { if (confirm("删除项目「" + name + "」？其待办保留在日常待办中。")) { state.projects = state.projects.filter(function (p) { return p.name !== name; }); } }
      else { state.projects.push({ name: name }); }
      save(); render(); toast(exist ? "已删除项目" : "已添加项目");
    };
    $("#batchAddBtn").onclick = batchAdd;
    $("#exportBtn").onclick = exportCsv;
    $("#multiBtn").onclick = function () { multi = true; selected = {}; $("#multiBtn").style.display = "none"; $("#selAllBtn").style.display = ""; render(); };
    $("#selAllBtn").onclick = function () {
      var all = currentTasks(); var allSel = all.every(function (t) { return selected[t.id]; });
      all.forEach(function (t) { if (allSel) { delete selected[t.id]; } else { selected[t.id] = true; } });
      render();
    };
    $("#batchDone").onclick = batchDone; $("#batchDel").onclick = batchDelete; $("#batchCat").onclick = batchRecat;

    // 点击弹窗外区域关闭
    ["#editSheet", "#strongSheet", "#syncSheet", "#themeSheet", "#menuSheet"].forEach(function (s) {
      $(s).addEventListener("click", function (e) { if (e.target === this) { closeSheet(s); } });
    });
  }

  // 切换视图：mode = "daily" | "project"（与桌面端 ViewMode 对齐）
  function switchView(mode) {
    viewMode = mode;
    activeCategory = "全部";
    if (mode === "project") {
      var names = state.projects.map(function (p) { return p.name; });
      if (names.indexOf(scope) === -1) { scope = names.length ? names[0] : DAILY_SCOPE; }
      loadScope();
    } else {
      scope = DAILY_SCOPE;
      loadScope();
    }
    var isProject = mode === "project";
    $("#tabDaily").classList.toggle("active", !isProject);
    $("#tabProject").classList.toggle("active", isProject);
    $("#projBar").classList.toggle("show", isProject);
    // 与桌面端 _apply_view_mode 对齐：项目视图隐藏日常的添加按钮与分类栏
    $("#addBtn").style.display = isProject ? "none" : "";
    $("#chipRow").style.display = isProject ? "none" : "";
    if (multi) { multi = false; selected = {}; $("#multiBtn").style.display = ""; $("#selAllBtn").style.display = "none"; }
    render();
  }

  // ------------------------------------------------------------ 启动
  function init() {
    load();
    purgeStaleTombstones();
    fillCategoryOptions();
    bindEvents();
    applyTheme();
    switchView("daily");
    if (navigator.serviceWorker) {
      navigator.serviceWorker.register("sw.js").catch(function () {});
    }
    if (state.settings.serverUrl) { setTimeout(push, 1500); }
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", init); }
  else { init(); }
})();
