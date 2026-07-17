# 把西瓜todo发布到 GitHub，让用户网页下载

目标：你有一个免费网站页面，用户打开就能选自己系统的版本下载；你以后更新，
只要上传代码 + 打个版本号，云端自动打包 Windows + Mac 两个版本并挂到下载页。

---

## 一、注册 GitHub 账户（一次性，约 5 分钟）

1. 打开 https://github.com
2. 点右上角 **Sign up**，用邮箱注册，设置用户名和密码
3. 按提示完成邮箱验证即可

> 用户名会出现在你的网址里，例如用户名是 `xigua`，
> 那你的下载页将来就是 `https://github.com/xigua/watermelon-todo/releases`

---

## 二、装一个上传工具（二选一）

**方式 A（推荐新手）：GitHub Desktop 图形界面**
1. 下载安装 https://desktop.github.com
2. 登录你的 GitHub 账户

**方式 B：命令行 Git**（你已装 git，会用命令行就选这个）

---

## 三、建仓库 + 上传代码（一次性）

### 用 GitHub Desktop（方式 A）
1. 菜单 `File → Add Local Repository`，选中你的项目文件夹 `d:\yujinyue.6\Desktop\ai`
2. 若提示"这里还不是仓库"，点 **Create a Repository**
3. 填仓库名，例如 `watermelon-todo`，勾选 Public（公开）
4. 点 **Publish repository** 上传到 GitHub

### 用命令行（方式 B）
在项目根目录 `d:\yujinyue.6\Desktop\ai` 依次执行：

```bash
git init
git add .
git commit -m "首次上传西瓜todo"
```

然后去 GitHub 网页点 **New repository** 建一个空仓库（名字如 `watermelon-todo`，选 Public），
建好后按页面提示执行（把下面 URL 换成你自己的）：

```bash
git remote add origin https://github.com/你的用户名/watermelon-todo.git
git branch -M main
git push -u origin main
```

---

## 四、发布第一个版本（生成下载页）

代码传上去后，**打一个版本标签**就会自动打包 + 生成下载页。

### 用 GitHub Desktop
菜单 `History` 区域右键最新提交 → `Create Tag`，标签填 `v2.0` → 再 Push。

### 用命令行
```bash
git tag v2.0
git push origin v2.0
```

推上去后：
1. 打开你的仓库网页，点顶部 **Actions**，会看到"打包并发布西瓜todo"正在跑（约 5-10 分钟）
2. 跑完后，点顶部 **Releases**，就能看到 `西瓜todo v2.0` 下载页，里面挂着：
   - `西瓜todo.exe`（Windows 用户下载）
   - `西瓜todo-mac.zip`（Mac 用户下载）

**把这个 Releases 网址发给用户即可**，他们点对应文件就能下载。

---

## 五、以后怎么更新（日常流程）

每次改完代码，重复三步：

```bash
git add .
git commit -m "这次改了什么"
git push
git tag v2.1      # 版本号往上加：v2.1、v2.2、v3.0……
git push origin v2.1
```

云端自动重新打包，下载页多出一个新版本，老版本仍保留，用户可自由选择。

> ⚠️ 版本号标签不能重复。每次发新版都要用一个**没用过的**号（如 v2.0→v2.1→v2.2）。

---

## 六、用户下载后的使用说明（可转发给用户）

- **Windows 用户**：下载 `西瓜todo.exe`，双击即用。
- **Mac 用户**：下载 `西瓜todo-mac.zip`，解压，把"西瓜todo.app"拖进"应用程序"。
  首次打开若提示"无法验证开发者"：在 App 上**右键 → 打开**，
  或到"系统设置 → 隐私与安全性 → 仍要打开"。

---

## 常见问题

**Q：Actions 打包失败/红叉怎么办？**
点进那次运行，看哪个步骤红了，把报错发我，我帮你改。

**Q：我不想让代码公开怎么办？**
私有仓库也能做，但下载页对外访问要额外设置，告诉我再帮你调整。

**Q：能有自己独立域名的下载页吗？**
可以进一步用 GitHub Pages 做一个美观的下载主页，需要的话再说。

**Q：数据（我的待办）会被上传吗？**
不会。程序数据存在你电脑的用户目录（不在代码文件夹里），上传的只有程序代码。