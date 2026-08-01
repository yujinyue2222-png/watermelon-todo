/**
 * 离线缓存。
 *
 * 注意：Service Worker 只能在安全上下文（HTTPS 或 localhost）注册，
 * 通过裸 HTTP 访问时浏览器会拒绝，页面会自动跳过注册——功能照常，
 * 只是没有离线缓存。等服务端上了 HTTPS，这个文件就会自动生效。
 *
 * 策略：
 * - 应用外壳（HTML/JS/图标）走「网络优先、失败回落缓存」：既能离线打开，
 *   又不会把用户永久钉死在旧版本上；
 * - ``/api/`` 一律走网络，绝不缓存，否则会读到过期的同步数据。
 *
 * 为什么不用「缓存优先」：那样只改 app.js 时本文件字节不变，浏览器认为
 * Service Worker 没更新，install 不会重跑、旧缓存不会失效，用户永远拿不到修复。
 * BUILD_ID 会在部署时被替换成本次提交号，保证每次发布都换一个缓存名。
 */
const BUILD_ID = "dev";
const CACHE_NAME = "watermelon-todo-v3-" + BUILD_ID;
const SHELL_FILES = ["./", "./index.html", "./app.js", "./manifest.json", "./icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_FILES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") { return; }

  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) {
    return;   // 同步接口交给浏览器直连，不做任何缓存
  }

  event.respondWith(
    fetch(request).then((response) => {
      // 只缓存正常响应：部署过程中拿到的 404/500 被缓存下来会一直坏着
      if (response && response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME)
          .then((cache) => cache.put(request, copy))
          .catch(() => undefined);
      }
      return response;
    }).catch(() => (
      // 断网：回落到缓存；导航请求找不到对应条目时兜底给首页
      caches.match(request).then((hit) => hit || caches.match("./index.html"))
    ))
  );
});
