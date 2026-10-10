/** Small dependency-free Chromium CDP smoke against disposable local Next only.
 * This is browser-level regression evidence, not a WCAG or mobile-device audit.
 */
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const paths = ["/", "/capabilities", "/plans", "/data-handling", "/faq"];
const viewports = [320, 375, 768, 1280];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function chromeBinary() {
  for (const binary of [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
  ]) {
    if (spawnSync("which", [binary], { encoding: "utf8" }).status === 0)
      return binary;
  }
  throw Error("Chrome/Chromium is required; browser checks may not be silently skipped.");
}

class Devtools {
  constructor(socket) {
    this.socket = socket;
    this.id = 0;
    this.pending = new Map();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      const target = this.pending.get(message.id);
      if (!target) return;
      clearTimeout(target.timeout);
      this.pending.delete(message.id);
      if (message.error) target.reject(Error(JSON.stringify(message.error)));
      else target.resolve(message.result);
    });
    socket.addEventListener("close", () => {
      for (const request of this.pending.values()) {
        clearTimeout(request.timeout);
        request.reject(Error("Browser disconnected during validation."));
      }
      this.pending.clear();
    });
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(Error(`Browser command timed out: ${method}`));
      }, 10000);
      this.pending.set(id, { resolve, reject, timeout });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async js(expression) {
    const output = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (output.exceptionDetails)
      throw Error(`Browser JS error: ${output.exceptionDetails.text}`);
    return output.result.value;
  }
  async key(key, code, keyCode) {
    await this.send("Input.dispatchKeyEvent", {
      type: "keyDown",
      key,
      code,
      windowsVirtualKeyCode: keyCode,
    });
    await this.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key,
      code,
      windowsVirtualKeyCode: keyCode,
    });
  }
}

async function run(origin) {
  const target = new URL(origin);
  assert.equal(target.protocol, "http:");
  assert.ok(["localhost", "127.0.0.1"].includes(target.hostname));
  assert.equal(target.pathname, "/");
  assert.equal(target.search, "");
  assert.equal(target.hash, "");
  const dir = await mkdtemp(join(tmpdir(), "vsn-browser-smoke-"));
  let chrome;
  let ws;
  try {
    chrome = spawn(
      chromeBinary(),
      [
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
        "--no-proxy-server",
        "--remote-debugging-port=0",
        `--user-data-dir=${dir}`,
        "about:blank",
      ],
      { stdio: "ignore" },
    );
    let port;
    for (let i = 0; i < 100; i++) {
      if (chrome.exitCode !== null)
        throw Error(`Browser exited before startup (${chrome.exitCode}).`);
      try {
        const active = (
          await readFile(join(dir, "DevToolsActivePort"), "utf8")
        ).split("\n");
        port = Number(active[0]);
        if (port > 0) break;
      } catch {
        // Chrome has not published a port yet.
      }
      await delay(80);
    }
    assert.ok(port, "Browser did not publish a DevTools port.");
    const tabResponse = await fetch(
      `http://127.0.0.1:${port}/json/new?about:blank`,
      { method: "PUT" },
    );
    assert.equal(tabResponse.status, 200);
    const tab = await tabResponse.json();
    ws = new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", resolve, { once: true });
      ws.addEventListener("error", reject, { once: true });
    });
    const cdp = new Devtools(ws);
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Page.bringToFront");
    await cdp.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    for (const width of viewports) {
      await cdp.send("Emulation.setDeviceMetricsOverride", {
        width,
        height: 850,
        deviceScaleFactor: 1,
        mobile: width <= 375,
      });
      for (const path of paths) {
        const navigated = await cdp.send("Page.navigate", {
          url: target.origin + path,
        });
        if (navigated.errorText)
          throw Error(`Cannot navigate ${path}: ${navigated.errorText}`);
        let ready = false;
        for (let i = 0; i < 80; i++) {
          ready = await cdp.js(
            `location.pathname === ${JSON.stringify(path)} && document.readyState === "complete" && !!document.querySelector("main h1")`,
          );
          if (ready) break;
          await delay(80);
        }
        assert.ok(ready, `Browser page did not load: ${width}px ${path}`);
        const measured = await cdp.js(`(() => {
          const main = document.querySelector("main");
          const skip = document.querySelector('a.skip[href="#main"]');
          const link = document.querySelector(".marketing-primary");
          const nav = document.querySelector('nav[aria-label="Primary navigation"]');
          return {
            width: innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            titleCount: document.querySelectorAll("main h1").length,
            skipValid: !!skip && main.id === "main" && main.tabIndex === -1,
            navCount: nav ? nav.querySelectorAll("a").length : 0,
            faqCount: document.querySelectorAll("details > summary").length,
            noindex: !!document.querySelector('meta[name="robots"][content*="noindex"]'),
            linkMotion: link ? getComputedStyle(link).transitionDuration : "none",
          };
        })()`);
        assert.ok(
          measured.scrollWidth <= measured.width + 1,
          `Horizontal overflow ${path} ${width}px: ${JSON.stringify(measured)}`,
        );
        assert.equal(measured.titleCount, 1, `${path} ${width}px headings`);
        assert.ok(measured.skipValid, `${path} ${width}px skip target`);
        assert.ok(measured.navCount >= 5, `${path} ${width}px navigation`);
        assert.equal(
          measured.faqCount,
          path === "/faq" ? 7 : 0,
          `${path} FAQ`,
        );
        assert.ok(measured.noindex, `${path} noindex`);
        if (path === "/") {
          assert.ok(
            ["0s", "0ms"].includes(measured.linkMotion),
            `Reduced-motion override ignored: ${measured.linkMotion}`,
          );
          await cdp.key("Tab", "Tab", 9);
          assert.equal(
            await cdp.js('document.activeElement?.className === "skip"'),
            true,
            `${width}px: first Tab should reach Skip to content`,
          );
          await cdp.key("Enter", "Enter", 13);
          assert.equal(
            await cdp.js(
              'location.hash === "#main" && document.activeElement?.id === "main"',
            ),
            true,
            `${width}px: Enter on Skip to content must focus main`,
          );
        }
        if (path === "/faq") {
          const point = await cdp.js(`(() => {
            const summary = document.querySelector("details summary");
            summary.scrollIntoView({ block: "center" });
            summary.focus();
            const rect = summary.getBoundingClientRect();
            return {
              focused: document.activeElement === summary,
              x: rect.left + rect.width / 2,
              y: rect.top + rect.height / 2,
            };
          })()`);
          assert.ok(point.focused, `${width}px FAQ summary must accept focus`);
          await cdp.send("Input.dispatchMouseEvent", {
            type: "mousePressed",
            x: point.x,
            y: point.y,
            button: "left",
            clickCount: 1,
          });
          await cdp.send("Input.dispatchMouseEvent", {
            type: "mouseReleased",
            x: point.x,
            y: point.y,
            button: "left",
            clickCount: 1,
          });
          let expanded = false;
          for (let i = 0; i < 20; i++) {
            expanded = await cdp.js('document.querySelector("details").open');
            if (expanded) break;
            await delay(50);
          }
          assert.equal(expanded, true, `${width}px FAQ click must disclose answer`);
        }
      }
    }
    console.log(
      `PASS: ${viewports.length * paths.length} real Chromium public page/viewport checks, skip-link keyboard, FAQ click/focus, reduced motion and horizontal overflow`,
    );
  } finally {
    if (ws) ws.close();
    if (chrome && chrome.exitCode === null) chrome.kill("SIGTERM");
    await delay(150);
    await rm(dir, { recursive: true, force: true });
  }
}

if (process.argv.length !== 3) {
  console.error("Usage: node scripts/browser-smoke.mjs http://localhost:<port>");
  process.exit(2);
}
run(process.argv[2]).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
