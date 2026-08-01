# 🍉 西瓜todo v3

桌面待办工具（PySide6）+ 手机端网页 + 自建同步服务，支持**按同步码多端同步**。

v3 目录是自包含的：不引用 `v2/` 或仓库里任何其他目录的文件。

```
桌面端(Win/Mac)  ─┐
                  ├─→  47.120.58.231:52121  ←─  手机端网页(iOS/Android)
本地 JSON 缓存    ─┘     纯标准库 + SQLite        localStorage
```

## 快速开始

**桌面端**

```bash
cd v3
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py            # 加 --debug 输出调试日志
```

**同步服务**（服务器上，**不需要装任何第三方库**）

```bash
cd v3
python3 -m server --host 0.0.0.0 --port 52121 --web web
```

**测试**（只依赖标准库，不用装 PySide6）

```bash
cd v3
python -m unittest discover -s tests -t . -v     # 88 个用例，含端到端同步
```

## 架构

```
run.py                  桌面端入口：解析参数 → 初始化日志 → 启动界面
assets/                 图标与 SVG 素材（随程序分发，只读）

backend/                ← 不 import 任何 GUI 库，可单独测试/复用
├── api.py              TodoBackend 门面：前后端唯一交汇点
├── core/               常量、路径、平台判断、日志、时间工具
├── models/             Task / SubTask / StrongRemind / AppConfig + 取值枚举
├── repositories/       JSON 持久化（原子写入、损坏文件兜底）
├── services/           业务规则：待办、项目、统计、提醒、导出、批量解析、更新检查
├── sync/               多端同步：HTTP 客户端 + 增量合并引擎
└── system/             开机自启

frontend/               ← 只负责显示与交互，数据全部经由 TodoBackend
├── application.py      启动引导：单实例、字体、快捷键、检查更新
├── sync_controller.py  同步调度：定时器 + 后台线程
├── native/             窗口层级/焦点等平台差异修补、全局快捷键
├── theme/              配色方案、主题管理、样式表（QSS）
├── widgets/            任务卡片、流式布局、日历、下拉框、内联编辑行等
├── dialogs/            日期选择、编辑、批量添加、导出、同步设置、主题市场等
└── windows/            主窗口、桌面悬浮小西瓜

server/                 ← 同步服务，纯标准库，可单独拷到服务器
├── database.py         SQLite 存储（按用户维度的增量序号）
├── http_api.py         HTTP 路由 + 静态网页托管
├── __main__.py         启动入口（python3 -m server）
└── watermelon-sync.service   systemd 单元

web/                    ← 手机端网页（PWA），由 server 托管
tests/                  后端与同步的单元测试
```

### 依赖方向

```
frontend  ──►  backend.api.TodoBackend  ──►  services  ──►  repositories  ──►  JSON
                                        └──►  sync      ──►  HTTP        ──►  server
```

只允许从上往下依赖。前端不读写文件、不解析日期、不做统计口径判断；
后端不认识任何 Qt 类型；服务端不理解待办的业务字段。

## 多端同步

### 怎么用

1. 桌面端点标题栏的 **☁ → 同步设置**
2. 勾选「启用多端同步」，点「生成」得到一个同步码，点「复制」
3. 在另一台设备（电脑或手机）填**同一个同步码**，保存
4. 之后自动同步：改完 3 秒后推一次，另外每分钟对齐一次，切回前台也会同步

同步码就是身份凭证，**没有密码**——服务端不做账号校验，谁拿到同步码就能读写这份数据。
所以默认生成的是 22 位随机码（约 128 位熵），别贴到公开的地方。

### 怎么实现的

- **离线优先**：本地 JSON 始终是界面的数据源，断网照常增删改，联网后补齐
- **冲突规则**：同一条待办以 `updated_at`（毫秒时间戳）更大的一方为准（后写覆盖）。
  **时间戳打平时以服务端为准**：服务端拒收，客户端接受远端版本。两边判定方向
  必须一致，否则同一毫秒内改同一条的两台设备会各执己见、永久分叉
- **本地时间戳严格递增**：毫秒精度下连改两次可能落在同一毫秒，`touch()` 会强制
  加 1，避免第二次编辑被服务端当成陈旧数据丢掉
- **删除用墓碑**：删除只是把 `deleted` 置为 True 并保留记录，否则另一台离线设备
  再上线时会把已删的待办同步回来。墓碑本地留 45 天、服务端留 60 天后清理
- **一次往返**：`POST /api/sync` 同时完成「上传本地改动」和「拉取远端改动」
- **先落盘再推游标**：拉回来的数据写盘失败时游标保持不动，下次重试。反过来的话
  这批改动会因为 `server_seq > cursor` 而再也不会下发
- **两种拒绝要分开**：`rejected` 表示服务端已有更新的版本（可以不再推），
  `refused` 表示服务端没能存下（必须保留脏标记重试）。混为一谈会静默丢数据
- **客户端时钟会被封顶**：超出服务端时钟 5 分钟的时间戳会被压回来，
  否则一台日期错乱的设备能写出一条谁都改不动的待办
- **服务端不懂业务**：整条待办以 JSON 原样存一列，服务端只看
  `id` / `updated_at` / `deleted`。以后客户端加字段不用改服务端、不用做数据库迁移
- **提醒不同步**：「已提醒过」是每台设备各自的记账，手机弹过不代表电脑不该弹

### 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查，返回版本与统计 |
| POST | `/api/sync` | 推拉合并，body 为 `{user_id, since, changes}` |
| GET | `/` 及其他 | 手机端网页（启动时带 `--web` 才有） |

## 服务器部署

在 47.120.58.231 上（假设是 Linux + systemd，机器上有 python3 ≥ 3.7、SQLite ≥ 3.24）：

> SQLite 版本是硬要求，同步用到了 UPSERT 语法（SQLite 3.24 / 2018 年起支持）。
> Ubuntu 18.04（3.22）、Debian 9（3.16）需要先升级，否则服务能起来但每次同步都报错。
> 服务启动时会自检并直接报错退出，不会让你摸不着头脑。

```bash
# 1. 把 v3 的 server 和 web 传上去
scp -r v3/server v3/web root@47.120.58.231:/opt/watermelon/

# 2. 建一个专用账号（服务不以 root 运行）
ssh root@47.120.58.231
useradd --system --no-create-home --shell /usr/sbin/nologin watermelon
chown -R watermelon:watermelon /opt/watermelon

# 3. 装成系统服务
cp /opt/watermelon/server/watermelon-sync.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now watermelon-sync
systemctl status watermelon-sync        # 确认 active (running)

# 4. 放行端口（按你的云厂商安全组 + 本机防火墙都要放）
firewall-cmd --add-port=52121/tcp --permanent && firewall-cmd --reload
# Ubuntu: ufw allow 52121/tcp

# 5. 验证
curl http://47.120.58.231:52121/api/health
```

跑起来后：

- 手机上浏览器打开 `http://47.120.58.231:52121/`，「添加到主屏幕」即可当 App 用
- 看日志：`journalctl -u watermelon-sync -f`
- 数据库：`/var/lib/watermelon/sync.db`，**备份就是拷这一个文件**

资源占用：常驻内存约 15-20MB（systemd 单元里限了 256MB / 50% CPU 做保险）。
不需要 nginx、不需要 pip install、不需要 Docker。

### 想再加一道门

同步码不慎泄露、或者想避免陌生人往你服务器写数据时，可以开一个共享令牌：

```bash
# 编辑 /etc/systemd/system/watermelon-sync.service，取消这行注释并改成随机串
Environment=WATERMELON_ACCESS_TOKEN=你的随机串
systemctl daemon-reload && systemctl restart watermelon-sync
```

然后在桌面端「同步设置 → 访问令牌」和手机端同一位置填上同一个串。
开了令牌之后 `/api/health` 也要带令牌才能读（它会返回用户数与库大小）。

## 自动打包（GitHub Actions）

工作流在仓库根目录 `.github/workflows/`（CI 配置必须放在仓库根，不能放进 v3）：

| 文件 | 作用 | 触发 |
|------|------|------|
| `test-v3.yml` | 只跑后端与同步测试（几秒钟） | 改动 `v3/**` 的 push / PR |
| `build-release-v3.yml` | 测试 + 打 Win/Mac 包 + 发 Release | 推 `v3-*` tag，或手动 Run workflow |
| `deploy-web-v3.yml` | 把 `v3/web` 发到 GitHub Pages | 仅手动（见下方限制） |

**普通 `git push` 不会打包**，只跑测试。要拿到安装包必须推一个 tag：

```bash
git add . && git commit -m "v3 首个版本"
git push
git tag v3-1.0 && git push origin v3-1.0     # 这一步才会打包并创建下载页
```

约 10-15 分钟后，仓库首页右侧 **Releases** 会出现下载页，包含：

- `西瓜todo-3.7-win版-Setup.exe`（Windows 安装版）
- `西瓜todo-3.7-win版-便携版.exe`（Windows 免安装）
- `西瓜todo-3.7-mac版.dmg`（macOS）

只想试试打包、先不发布：Actions 页面 → 「打包并发布西瓜todo v3」→ Run workflow，
产物在该次运行的 **Artifacts** 里，不会创建 Release。

### 第一次发版前必须做的两件事

1. **Settings → Actions → General → Workflow permissions** 选
   **Read and write permissions** 并保存。否则 CI 没权限创建 Release，
   打包会成功但发布那一步失败。
2. 仓库里旧的 `build-release-v2.yml` 监听 `v*`，也会被 `v3-*` 命中而一起跑
   （它会去打 v2 的包）。不想让它跑就去 Actions 页面把那个 workflow 关掉。

> 打出来的包都没有数字签名（签名要交年费），首次打开时系统会拦一下：
> Windows 点「更多信息」→「仍要运行」；macOS 到「系统设置 → 隐私与安全性」点「仍要打开」。

## 已知限制

这几条是硬约束，先说清楚免得踩坑：

1. **iOS 不能用 PySide6 打包。** Qt 本身支持 iOS，但 Qt for Python 没有 iOS
   部署链路。所以移动端走的是网页方案（`web/`），用「添加到主屏幕」当 App。
   好处是不用 Apple 开发者账号（$99/年）、不用过审、改完刷新就更新。
   如果以后一定要上 App Store，移动端得用别的技术栈重写（Flutter / 原生）。

2. **裸 HTTP 下没有离线缓存。** 浏览器要求 Service Worker 只能在安全上下文
   （HTTPS 或 localhost）注册，所以通过 `http://` 访问时网页会自动跳过注册——
   功能都正常，只是断网打不开页面（已存的数据仍在 localStorage 里）。

3. **GitHub Pages 版无法同步。** Pages 是 HTTPS，浏览器禁止 HTTPS 页面请求
   HTTP 接口。所以手机请直接访问 `http://47.120.58.231:52121/`，
   页面与接口同源，没有这个问题。

4. **同步码等于密码。** 服务端不做账号密码校验，泄露了对方就能读写你的待办。
   在意的话开上面说的访问令牌，或者继续往下看 HTTPS 升级。

5. **冲突可能丢一次编辑。** 后写覆盖不是 CRDT：两端都离线、同时改**同一条**
   待办时，较早那次编辑会被覆盖。改不同待办、或一端在线时都不受影响。

### 升级到 HTTPS（推荐但需要域名）

上面 2、3、4 三条的根因都是裸 HTTP。有域名的话：

1. 把域名 A 记录指向 47.120.58.231
2. 装 nginx + certbot 申请证书，反代到 `127.0.0.1:52121`
3. 服务改成只监听本机：`--host 127.0.0.1`
4. 桌面端/手机端把服务器地址改成 `https://你的域名`

之后离线缓存生效、Pages 版也能同步、传输全程加密。

## 数据存放位置

**客户端**（待办与配置不跟着程序走，卸载或移动程序都不会丢）：

| 平台 | 路径 |
|------|------|
| Windows | `%APPDATA%\DesktopTodo\` |
| macOS | `~/Library/Application Support/DesktopTodo/` |
| Linux | `~/.local/share/DesktopTodo/` |

其中 `todo_data.json` 是待办，`todo_config.json` 是配置，`app.log` 是运行日志。
文件格式与 v2 兼容，v2 的数据可以直接被 v3 读取（旧字段自动补齐，
例如老版本的「紧急」优先级会并入 P1）。

**服务端**：`/var/lib/watermelon/sync.db`（SQLite 单文件）。

## 功能一览

- **待办**：新建/编辑/完成/删除、置顶、分类、优先级（P0/P1/P2/重要/普通）、
  截止日期与具体时间点、备注、小步骤拆解
- **循环**：每日 / 工作日 / 每周 / 每月 / 每年，可设循环结束日期，完成后自动生成下一期
- **提醒**：按档位提前提醒（10 分钟 ~ 3 天）+ 到期提醒；「强提醒」可在截止前的
  时间窗内按间隔反复提醒，支持次数上限与悬浮球浮窗
- **项目**：日常待办与项目待办两个独立视图，项目可重命名/删除，
  支持批量粘贴（含从 Excel 直接粘贴）与重复检测
- **批量操作**：多选后批量完成 / 改分类 / 删除
- **导出**：按日期区间与完成状态筛选，导出 CSV（Excel 直接打开不乱码）或 TXT
- **界面**：20 套主题 + DIY 配色 + 自定义背景图、窗口置顶/折叠/边缘拉伸、
  系统托盘、全局快捷键、桌面悬浮小西瓜（待办越多走得越快，完成时撒花庆祝）
- **多端同步**：见上文
- **手机端**：新增/完成/删除/编辑（内容、截止、分类、优先级、备注、置顶）、
  按日常/项目筛选。循环、小步骤、强提醒等桌面端设置在手机上**原样保留**，
  不会被编辑操作抹掉

## 相比 v2 的改动

结构之外，顺手修掉了几个问题：

1. **源码模式的开机自启失效**：v2 写死了已不存在的 `todo_qt.py`，现在指向 `run.py`
2. **批量添加选「继续新增」无效**：v2 内部总会跳过同名待办，现在由参数控制
3. **数据文件写坏的风险**：改为「写临时文件 + 原子替换」，写入中断不会留下半截 JSON
4. **异常被吞掉**：v2 大量 `except Exception: pass`，现在按具体异常捕获并写日志
5. **任务 ID 可能撞车**：v2 用纯毫秒时间戳，多端离线各自新建时会撞；
   现在加了随机后缀（`1754000000123-a1b2c3`）
6. 清理了失效代码：未使用的隐藏输入控件、没有入口的关键字搜索、
   从未被调用的 `_split_batch_note` 等

## 一轮全面排查后修掉的问题

上线前又把同步链路、日期计算与服务端安全过了一遍，以下都补了回归测试：

**同步（会静默丢数据的那类）**

1. **平局判定两边相反导致永久分叉**：服务端在 `updated_at` 相等时判自己赢，
   两个客户端却都判自己赢。同一毫秒内改同一条待办的两台设备从此各执己见，
   而且脏标记已被清掉，永远不会自愈。现在统一成「打平以服务端为准」
2. **同一毫秒内的第二次编辑会被丢掉**：`touch()` 现在保证时间戳严格递增
3. **容量拒绝被当成推送成功**：服务端没存下的记录清掉了脏标记，从此只剩本机有；
   如果是墓碑，删除还会在 45 天后彻底失传。现在 `refused` 与 `rejected` 分开返回
4. **游标先于数据落盘**：写盘失败时游标已经越过那批改动，它们再也不会下发。
   桌面端与手机端都改成「先存数据，成功了才推游标」
5. **推送被拒时拿不到权威版本**：服务端现在会把自己那份一并回发
6. **时钟错乱的设备能写出改不动的待办**：客户端时间戳按服务端时钟封顶

**服务端安全**

7. **目录穿越可绕过**：原来用字符串前缀判断，`web_root` 为 `/opt/app/web` 时
   `/opt/app/web-secret/x` 会被放行；改成按路径层级判断，并补上百分号解码
8. **服务以 root 运行**：systemd 单元加了 `User=`，加固项也收紧了
9. **`/api/health` 不校验令牌**：它会返回用户数、待办数与库大小
10. **令牌用 `==` 比较**：换成 `hmac.compare_digest`
11. **数据库异常会掐断连接**：客户端只能看到「连不上服务器」，现在返回 503
12. **并发连接数无上限**：几十个大请求就能顶穿 `MemoryMax` 触发重启循环

**日期与提醒**

13. **每月/每年循环会「粘住」**：1 月 31 日过一次 2 月后永远停在 28 号，
    2 月 29 日到了闰年也回不去。现在把锚定日存在 `recur_anchor` 里传下去
14. **「下周X」多跳一周**：从周五解析「下周一」会落到两周后
15. **改期后强提醒哑火**：`strong.count` / `last` 从不重置
16. **「到期当天」只在 23:59 响**：只填日期时改为当天上午提醒
17. **提醒记账会触发一次空同步**

**健壮性**

18. 畸形服务器地址（缺 `http://`）抛 `ValueError` 打死同步线程，界面毫无提示
19. 一条字段类型坏掉的记录会让程序直接打不开
20. 只读数据目录不会触发「退回程序目录」的兜底，程序看着正常却什么都存不下
21. `v3.7-rc1` 被解析成 `(3, 71)`，比正式版还「新」
22. macOS LaunchAgent 手拼 XML，路径含 `&` 时写出非法 plist 却报告成功

**界面与手机端**

23. 主题市场进 DIY 配色再返回会 `RuntimeError`（`setWidget` 已删除旧控件）
24. 排队的手动同步被静默丢弃；退出时等待时间短于 HTTP 超时，可能 `qFatal`
25. 没有任何项目时，项目视图的统计把日常待办全算了进去
26. 进度条动画每次刷新都新建且不释放，常驻托盘会一直堆积
27. 卡片嵌套的透明度效果导致 Qt 刷屏报 `QPainter` 警告并丢帧
28. 手机端命中同步轮次上限后 `syncing` 没复位，此后所有自动同步全部失效
29. Service Worker 缓存名写死且外壳走缓存优先，只改 `app.js` 时用户永远拿不到更新
30. 手机端不清理墓碑，`localStorage` 迟早写满，而写满会导致数据永久丢失
31. **非 cocoa 平台下启动直接段错误**：`window_effects.py` 只判断了操作系统是不是
    macOS，没判断 Qt 平台插件。`QT_QPA_PLATFORM=offscreen` 时 `sys.platform` 仍是
    darwin，但 `winId()` 返回的不是 NSView 指针，向它发 Objective-C 消息会
    段错误——而段错误是 `try/except` 拦不住的。这也正是界面一直没法做自动化测试的原因

### 界面部分怎么验证的

`tests/` 仍然只依赖标准库（CI 不装 PySide6），所以界面修复没有进单元测试。
验证方式是装上 PySide6 后用 `QT_QPA_PLATFORM=offscreen` 真实构建窗口并驱动交互，
逐条确认：主题市场重复重建不再抛异常、`_update_stats` 调用 60 次动画对象数
稳定在 6 个、刷新与删除时 `QPainter` 警告为 0 条、悬停切图标时布局不跳、
分类栏滚轮能滚动、`FlowLayout` 首个子项落在 (20, 20)、Retina 下图标填充率
从 58% 回到 94%、手动同步不会自我触发成死循环。修完第 31 条之后这套验证才跑得起来。
