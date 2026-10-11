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
    this.browserRequests = [];
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.method === "Network.requestWillBeSent") {
        this.browserRequests.push(message.params.request.url);
      }
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
        "--disable-dev-shm-usage",
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
    for (let i = 0; i < 250; i++) {
      if (chrome.exitCode !== null || chrome.signalCode !== null)
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
    await cdp.send("Network.enable");
    await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
    await cdp.send("Page.bringToFront");
    await cdp.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-motion", value: "reduce" }],
    });
    let peakBytes = 0;
    let peakRequests = 0;
    let contrastSamples = 0;
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
            touchTargets: [...document.querySelectorAll(
              "header .brand, header .site-nav a, .marketing-actions a"
            )].filter((node) => node.getClientRects().length > 0).map((node) => {
              const rect = node.getBoundingClientRect();
              return { label: node.textContent.trim(), width: rect.width, height: rect.height };
            }),
            faqCount: document.querySelectorAll("details > summary").length,
            noindex: !!document.querySelector('meta[name="robots"][content*="noindex"]'),
            linkMotion: link ? getComputedStyle(link).transitionDuration : "none",
            privateMarkerPresent:
              document.documentElement.innerHTML.includes("Foreign private marker") ||
              document.documentElement.innerHTML.includes("Synthetic &lt;workspace&gt;") ||
              document.documentElement.innerHTML.includes("synthetic-next-owner"),
          };
        })()`);
        // Deterministic byte/request envelope and computed visual contrast.
        // Do not gate CI on wall-clock paint timing on variable runner hardware.
        const quality = await cdp.js(`(() => {
          const resources = performance.getEntriesByType("resource");
          const documentTransfer = performance.getEntriesByType("navigation")[0]?.transferSize || 0;
          const bytes = documentTransfer + resources.reduce(
            (sum, item) => sum + item.transferSize, 0
          );
          const parseColor = (color) => {
            if (!/^rgba?\\(/.test(color)) return null;
            const matches = color.match(/[\\d.]+/g);
            if (!matches || matches.length < 3) return null;
            const values = matches.map(Number);
            return {
              rgb: values.slice(0, 3),
              alpha: values.length === 4 ? values[3] : 1,
            };
          };
          const backgroundOf = (element) => {
            for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
              const value = parseColor(getComputedStyle(ancestor).backgroundColor);
              if (value && value.alpha === 1) return value.rgb;
            }
            return [255, 255, 255];
          };
          const lightness = (rgb) => {
            const channels = rgb.map((value) => {
              const normalized = value / 255;
              return normalized <= 0.04045
                ? normalized / 12.92
                : ((normalized + 0.055) / 1.055) ** 2.4;
            });
            return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
          };
          const contrast = (one, two) => {
            const a = lightness(one);
            const b = lightness(two);
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          };
          const samples = [
            ".marketing-lead",
            ".marketing-kicker",
            ".marketing-disclosure",
            ".marketing-card p",
            ".marketing-tag",
            ".marketing-tag-built",
            ".faq-list summary",
            ".faq-list details p",
          ].flatMap((selector) =>
            [...document.querySelectorAll(selector)].filter((node) =>
              node.getClientRects().length > 0
            ).map((node) => {
              const foreground = parseColor(getComputedStyle(node).color);
              return {
                selector,
                value: foreground ? contrast(foreground.rgb, backgroundOf(node)) : 0,
              };
            })
          );
          return {
            bytes,
            requests: resources.length + 1,
            samples,
          };
        })()`);
        peakBytes = Math.max(peakBytes, quality.bytes);
        peakRequests = Math.max(peakRequests, quality.requests);
        contrastSamples += quality.samples.length;
        assert.ok(
          quality.bytes <= 1 * 1024 * 1024,
          `Page-weight regression ${path} ${width}px: ${quality.bytes} bytes`,
        );
        assert.ok(
          quality.requests <= 60,
          `First-party request regression ${path} ${width}px: ${quality.requests} requests`,
        );
        assert.ok(quality.samples.length >= 2, `Missing readability samples: ${path}`);
        for (const sample of quality.samples) {
          assert.ok(
            sample.value >= 4.5,
            `Text contrast regression ${path} ${width}px ${sample.selector}: ${sample.value.toFixed(2)}:1`,
          );
        }
        assert.ok(
          measured.scrollWidth <= measured.width + 1,
          `Horizontal overflow ${path} ${width}px: ${JSON.stringify(measured)}`,
        );
        assert.equal(measured.titleCount, 1, `${path} ${width}px headings`);
        assert.ok(measured.skipValid, `${path} ${width}px skip target`);
        assert.ok(measured.navCount >= 5, `${path} ${width}px navigation`);
        assert.ok(measured.touchTargets.length >= 7, `${path} ${width}px touch targets`);
        for (const target of measured.touchTargets) {
          assert.ok(
            target.width >= 24 && target.height >= 44,
            `Undersized navigation or marketing action ${path} ${width}px: ${JSON.stringify(target)}`,
          );
        }
        assert.equal(
          measured.faqCount,
          path === "/faq" ? 7 : 0,
          `${path} FAQ`,
        );
        assert.ok(measured.noindex, `${path} noindex`);
        assert.equal(
          measured.privateMarkerPresent,
          false,
          `${path} ${width}px anonymous browser must not embed workspace markers`,
        );
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
    const publicRequests = cdp.browserRequests.slice();
    // Disposable test-only Django session: no login to external services, no
    // real credentials, and never expose the cookie in arguments or logs.
    const privateSession = process.env.VSN_BROWSER_SMOKE_SESSION;
    const privateCsrf = process.env.VSN_BROWSER_SMOKE_CSRF;
    const draftPostOrigin = process.env.VSN_BROWSER_SMOKE_DRAFT_POST_ORIGIN;
    if (draftPostOrigin) {
      const posted = new URL(draftPostOrigin);
      assert.equal(posted.protocol, "http:");
      assert.equal(posted.hostname, target.hostname);
      assert.ok(posted.port && posted.pathname === "/" && !posted.search && !posted.hash);
    }
    const resetLink = process.env.VSN_BROWSER_SMOKE_RESET_LINK;
    if (resetLink) {
      assert.ok(draftPostOrigin, "Recovery fixture requires disposable Django.");
      const link = new URL(resetLink);
      assert.equal(link.protocol, "http:");
      assert.equal(link.origin, new URL(draftPostOrigin).origin);
      assert.match(link.pathname, /^\/accounts\/reset\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_-]+\/$/);
      assert.equal(link.search, "");
      assert.equal(link.hash, "");
    }
    const ownWorkspace = process.env.VSN_BROWSER_SMOKE_OWN_WORKSPACE;
    const foreignWorkspace = process.env.VSN_BROWSER_SMOKE_FOREIGN_WORKSPACE;
    const ownJob = process.env.VSN_BROWSER_SMOKE_OWN_JOB;
    const privateValues = [
      privateSession,
      privateCsrf,
      ownWorkspace,
      foreignWorkspace,
      ownJob,
    ];
    if (privateValues.some(Boolean)) {
      assert.ok(
        privateValues.every(Boolean),
        "Incomplete private browser smoke fixture.",
      );
      const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
      assert.ok(uuid.test(ownWorkspace) && uuid.test(foreignWorkspace) && uuid.test(ownJob));
      assert.notEqual(ownWorkspace, foreignWorkspace);
      assert.ok(/^[a-zA-Z0-9:_-]{24,160}$/.test(privateSession));

      async function inspectPrivate(path, requiredText, forbiddenTexts) {
        const outcome = await cdp.send("Page.navigate", {
          url: target.origin + path,
        });
        if (outcome.errorText) throw Error("Private browser page navigation failed.");
        let ready = false;
        for (let attempt = 0; attempt < 100; attempt++) {
          ready = await cdp.js(`(() => {
            if (location.pathname + location.search !== ${JSON.stringify(path)}) return false;
            if (document.readyState !== "complete") return false;
            const main = document.querySelector("main");
            if (!main) return false;
            return main.textContent.includes(${JSON.stringify(requiredText)});
          })()`);
          if (ready) break;
          await delay(80);
        }
        assert.ok(ready, `Private browser state unavailable: ${path}`);
        const state = await cdp.js(`(() => ({
          content: document.querySelector("main")?.textContent || "",
          scrollWidth: document.documentElement.scrollWidth,
          viewportWidth: innerWidth,
          titleCount: document.querySelectorAll("main h1").length,
          mainFocusable: document.querySelector("main")?.tabIndex === -1,
        }))()`);
        assert.equal(state.titleCount, 1, `Heading regression: ${path}`);
        assert.equal(state.mainFocusable, true, `Skip-target regression: ${path}`);
        assert.ok(
          state.scrollWidth <= state.viewportWidth + 1,
          `Private workspace horizontal overflow: ${path}`,
        );
        for (const forbidden of forbiddenTexts) {
          assert.equal(
            state.content.includes(forbidden),
            false,
            `Private browser data crossed authorization boundary: ${path}`,
          );
        }
      }

      async function clickVisible(selector) {
        const point = await cdp.js(`(() => {
          const control = document.querySelector(${JSON.stringify(selector)});
          if (!control) return null;
          control.scrollIntoView({block: "center"});
          const rect = control.getBoundingClientRect();
          return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
        })()`);
        assert.ok(point, `Missing interactive control: ${selector}`);
        for (const type of ["mousePressed", "mouseReleased"]) {
          await cdp.send("Input.dispatchMouseEvent", {
            type,
            x: point.x,
            y: point.y,
            button: "left",
            clickCount: 1,
          });
        }
      }
      async function waitForInteraction(condition, description) {
        for (let attempt = 0; attempt < (description.includes("draft POST") ? 250 : 100); attempt++) {
          if (await cdp.js(condition)) return;
          await delay(80);
        }
        const state = await cdp.js(`(() => ({
          path: location.pathname,
          heading: document.querySelector("main h1")?.textContent.trim() || null,
        }))()`);
        assert.fail(`Browser interaction did not reach expected state: ${description}; state=${JSON.stringify(state)}`);
      }

      for (const width of [320, 1280]) {
        await cdp.send("Emulation.setDeviceMetricsOverride", {
          width,
          height: 850,
          deviceScaleFactor: 1,
          mobile: width === 320,
        });
        await inspectPrivate("/dashboard", "Sign in to see your workspaces.", [
          "Synthetic <workspace>",
          "Foreign private marker",
          "Synthetic bakery",
        ]);
        const cookie = await cdp.send("Network.setCookie", {
          name: "sessionid",
          value: privateSession,
          url: target.origin,
          httpOnly: true,
          sameSite: "Lax",
          secure: false,
        });
        assert.equal(cookie.success, true, "Synthetic session cookie could not be set.");
        const csrfCookie = await cdp.send("Network.setCookie", {
          name: "csrftoken",
          value: privateCsrf,
          url: target.origin,
          httpOnly: false,
          sameSite: "Lax",
          secure: false,
        });
        assert.equal(csrfCookie.success, true, "Real test CSRF cookie could not be set.");
        await inspectPrivate("/dashboard", "Workspaces", [
          "Foreign private marker",
        ]);
        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}`,
          "Workspace overview",
          ["Foreign private marker"],
        );
        const authorizedContent = await cdp.js(
          'document.querySelector("main")?.textContent || ""',
        );
        assert.ok(authorizedContent.includes("Synthetic <workspace>"));
        assert.ok(authorizedContent.includes("Synthetic bakery"));
        // Opening search forms and paginated views must never dispatch,
        // reserve or create work. Assert native controls in a real browser.
        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}/search/new`,
          "Create draft search",
          ["Foreign private marker"],
        );
        const draftForm = await cdp.js(`(() => ({
          form: !!document.querySelector('form.search-form[method="post"]'),
          countries: [...document.querySelectorAll('input[name="countries"]')].map((x) => x.value),
          categories: !!document.querySelector('textarea[name="categories"][required]'),
          disabledPhone: !!document.querySelector('input[type="checkbox"][disabled][checked]'),
          submit: !!document.querySelector('button[type="submit"]'),
        }))()`);
        assert.equal(draftForm.form, true, "Draft must have explicit POST form.");
        assert.deepEqual(draftForm.countries, ["US", "CA"]);
        assert.equal(draftForm.categories, true);
        assert.equal(draftForm.disabledPhone, true);
        assert.equal(draftForm.submit, true);

        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}?status=draft`,
          "27 saved searches across all pages",
          ["Foreign private marker"],
        );
        const filtered = await cdp.js(`(() => ({
          selected: document.querySelector('select[name="status"]')?.value,
          next: [...document.querySelectorAll('nav[aria-label="Search pages"] a')].some(
            (a) => a.textContent.includes("Next page") && a.getAttribute("href").includes("status=draft")
          ),
        }))()`);
        assert.equal(filtered.selected, "draft");
        assert.equal(filtered.next, true, "Draft job pagination must retain its status filter.");

        // Exercise native form submission and actual Next-link pagination
        // instead of merely opening prepared URLs. Never submit a job.
        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}`,
          "Workspace overview",
          ["Foreign private marker"],
        );
        assert.equal(
          await cdp.js(`(() => {
            const select = document.querySelector('select[name="status"]');
            if (!select) return false;
            select.value = "draft";
            select.dispatchEvent(new Event("change", {bubbles: true}));
            return select.value === "draft";
          })()`),
          true,
          "Job status selector must allow selecting draft",
        );
        await clickVisible('form[method="get"] button[type="submit"]');
        await waitForInteraction(
          `(() => location.pathname === ${JSON.stringify(`/dashboard/workspaces/${ownWorkspace}`)}
            && new URLSearchParams(location.search).get("status") === "draft"
            && document.querySelector('select[name="status"]')?.value === "draft"
            && document.querySelectorAll('main span.badge').length === 25)()`,
          "Apply filter must navigate to the first 25 draft jobs",
        );
        await clickVisible('nav[aria-label="Search pages"] a[href*="after="]');
        await waitForInteraction(
          `(() => new URLSearchParams(location.search).has("after")
            && document.querySelectorAll("main span.badge").length === 2)()`,
          "Second page must show only the last two draft jobs",
        );
        const pageTwoState = await cdp.js(`(() => ({
          status: new URLSearchParams(location.search).get("status"),
          after: new URLSearchParams(location.search).get("after"),
          count: document.querySelectorAll("main span.badge").length,
          first: !![...document.querySelectorAll('nav[aria-label="Search pages"] a')].find(
            (a) => a.textContent.trim() === "First page"
          ),
          foreign: document.querySelector("main")?.textContent.includes("Foreign private marker"),
        }))()`);
        assert.equal(pageTwoState.status, "draft");
        assert.ok(uuid.test(pageTwoState.after || ""));
        assert.equal(pageTwoState.count, 2);
        assert.equal(pageTwoState.first, true);
        assert.equal(pageTwoState.foreign, false);
        await clickVisible('nav[aria-label="Search pages"] a[href*="status=draft"]:not([href*="after="])');
        await waitForInteraction(
          `(() => new URLSearchParams(location.search).get("status") === "draft"
            && !new URLSearchParams(location.search).has("after")
            && document.querySelectorAll("main span.badge").length === 25)()`,
          "First-page link must keep draft status without cursor",
        );

        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}/sources`,
          "Source configuration",
          ["Foreign private marker"],
        );
        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}/daily-plans`,
          "Saved daily plans",
          ["Foreign private marker"],
        );
        const plans = await cdp.js('document.querySelector("main")?.textContent || ""');
        assert.ok(plans.includes("27 stored daily plans across all pages"));
        assert.ok(plans.includes("not running schedules"));

        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}/jobs/${ownJob}`,
          "Saved search",
          ["Foreign private marker"],
        );
        if (draftPostOrigin && width === 1280) {
          // Genuine browser POST -> Django 303 -> first Next detail render.
          // Disposable synthetic form only; no job submission or source dispatch.
          await inspectPrivate(
            `/dashboard/workspaces/${ownWorkspace}/search/new`,
            "Create draft search",
            ["Foreign private marker"],
          );
          const prepared = await cdp.js(`(() => {
            const form = document.querySelector('form.search-form[method="post"]');
            const category = form?.querySelector('textarea[name="categories"]');
            const canada = form?.querySelector('input[name="countries"][value="CA"]');
            const token = form?.querySelector('input[name="draft_token"]');
            if (!form || !category || !canada || !token?.value) return false;
            category.value = "Synthetic browser-post salon";
            category.dispatchEvent(new Event("input", {bubbles: true}));
            return form.checkValidity();
          })()`);
          assert.equal(prepared, true, "Synthetic search form must validate before POST");
          await clickVisible('input[name="countries"][value="CA"]');
          const canadaSelected = await cdp.js(
            'document.querySelector(\'input[name="countries"][value="CA"]\')?.checked',
          );
          assert.equal(canadaSelected, true, "Canada must be selected by a real browser click.");
          await clickVisible('form.search-form button[type="submit"]');
          await waitForInteraction(
            `(() => {
              const prefix = ${JSON.stringify(`/dashboard/workspaces/${ownWorkspace}/jobs/`)};
              return location.pathname.startsWith(prefix)
                && location.pathname.length === prefix.length + 36
                && document.querySelector("main h1")?.textContent.trim() === "Saved search"
                && document.querySelector("main")?.textContent.includes("Synthetic browser-post salon");
            })()`,
            "First redirected draft POST must render the saved job",
          );
          const created = await cdp.js(`(() => ({
            id: location.pathname.split("/").at(-1),
            state: document.querySelector("main span.badge")?.textContent.trim(),
            foreign: document.querySelector("main")?.textContent.includes("Foreign private marker"),
          }))()`);
          assert.ok(uuid.test(created.id));
          assert.notEqual(created.id, ownJob);
          assert.equal(created.state, "draft");
          assert.equal(created.foreign, false);
          console.log("PASS: cross-origin browser draft POST -> initial Next job detail");
        }

        await inspectPrivate(
          `/dashboard/workspaces/${foreignWorkspace}`,
          "Information unavailable",
          ["Foreign private marker", "Synthetic <workspace>", "Synthetic bakery"],
        );
        await inspectPrivate(
          `/dashboard/workspaces/${foreignWorkspace}/search/new`,
          "Information unavailable",
          ["Foreign private marker", "Synthetic <workspace>", "Synthetic bakery"],
        );
        const foreignForm = await cdp.js(
          '!!document.querySelector("main form.search-form")',
        );
        assert.equal(foreignForm, false, "Foreign workspace must never render a form.");
        await cdp.send("Network.deleteCookies", {
          name: "sessionid",
          url: target.origin,
        });
        await inspectPrivate("/dashboard", "Sign in to see your workspaces.", [
          "Synthetic <workspace>",
          "Foreign private marker",
          "Synthetic bakery",
        ]);
        await inspectPrivate(
          `/dashboard/workspaces/${ownWorkspace}`,
          "Sign in to see your workspaces.",
          ["Synthetic <workspace>", "Foreign private marker", "Synthetic bakery"],
        );
      }

      if (draftPostOrigin) {
        // Synthetic browser-created account, never a real signup or email.
        // Prior authenticated fixture session was explicitly deleted above.
        await inspectPrivate("/account/sign-up", "Create account", [
          "Foreign private marker",
          "Synthetic bakery",
        ]);
        const signupReady = await cdp.js(`(() => {
          const form = document.querySelector("main form[method=post]");
          if (!form || !form.elements.namedItem("csrfmiddlewaretoken")?.value
              || form.elements.namedItem("native_signup")?.value !== "1") return false;
          const values = {
            username: "synthetic-browser-account",
            email: "browser-account@synthetic.invalid",
            workspace_name: "Synthetic signup workspace",
            password1: "Field#river75-polar%evergreen",
            password2: "Field#river75-polar%evergreen",
          };
          for (const [name, value] of Object.entries(values)) {
            const field = form.elements.namedItem(name);
            if (!field) return false;
            field.value = value;
            field.dispatchEvent(new Event("input", {bubbles: true}));
          }
          return form.checkValidity();
        })()`);
        assert.equal(signupReady, true, "Browser account form must validate before POST.");
        await clickVisible('main form[method="post"] button[type="submit"]');
        await waitForInteraction(
          `(() => location.pathname === "/dashboard"
            && document.querySelector("main h1")?.textContent.trim() === "Workspaces"
            && document.querySelector("main")?.textContent.includes("Synthetic signup workspace"))()`,
          "Synthetic signup POST must create a private workspace and sign in",
        );
        const newAccount = await cdp.js(`(() => ({
          foreign: document.querySelector("main")?.textContent.includes("Foreign private marker"),
          oldAccount: document.querySelector("main")?.textContent.includes("Synthetic bakery"),
        }))()`);
        assert.equal(newAccount.foreign, false);
        assert.equal(newAccount.oldAccount, false);
        await inspectPrivate(
          "/dashboard/workspaces/" + ownWorkspace,
          "Information unavailable",
          ["Synthetic bakery", "Synthetic signup workspace", "Foreign private marker"],
        );
        await cdp.send("Network.deleteCookies", {
          name: "sessionid",
          url: target.origin,
        });
        await inspectPrivate("/dashboard", "Sign in to see your workspaces.", [
          "Synthetic signup workspace",
          "Synthetic bakery",
        ]);
        console.log("PASS: real Chromium signup POST -> new isolated workspace -> logout denial");
        if (resetLink) {
          // Real Next link, Django recovery form and a single-use token taken
          // from a synthetic local email. No production mail or credentials.
          await cdp.send("Page.navigate", {
            url: new URL("/accounts/start-sign-in/", draftPostOrigin).href,
          });
          await waitForInteraction(
            '(() => location.pathname === "/account/sign-in" && !!document.querySelector(\'main a[href*="/accounts/password-reset/"]\'))()',
            "Native sign-in must expose password recovery",
          );
          await clickVisible('main a[href*="/accounts/password-reset/"]');
          await waitForInteraction(
            '(() => location.pathname === "/accounts/password-reset/" && document.querySelector("main h1")?.textContent === "Reset your password")()',
            "Recovery link must reach the Django reset form",
          );
          const unknownReady = await cdp.js(`(() => {
            const form = document.querySelector("main form[method=post]");
            const email = form?.elements.namedItem("email");
            if (!email || !form?.elements.namedItem("csrfmiddlewaretoken")?.value) return false;
            email.value = "unknown-recovery@synthetic.invalid";
            email.dispatchEvent(new Event("input", {bubbles: true}));
            return form.checkValidity();
          })()`);
          assert.equal(unknownReady, true, "CSRF-protected email form must validate.");
          await clickVisible('main form button[type="submit"]');
          await waitForInteraction(
            '(() => location.pathname === "/accounts/password-reset/sent/" && !!document.querySelector("main h1"))()',
            "Unknown email must get the same generic sent confirmation",
          );
          await cdp.send("Page.navigate", {url: resetLink});
          await waitForInteraction(
            '(() => location.pathname.endsWith("/set-password/") && document.querySelector("main h1")?.textContent === "Choose a new password")()',
            "Local email token must open one-use password form",
          );
          const ready = await cdp.js(`(() => {
            const form = document.querySelector("main form[method=post]");
            if (!form?.elements.namedItem("csrfmiddlewaretoken")?.value) return false;
            for (const name of ["new_password1", "new_password2"]) {
              const input = form.elements.namedItem(name);
              if (!input) return false;
              input.value = "Synthetic-browser-new-passphrase-9911";
              input.dispatchEvent(new Event("input", {bubbles: true}));
            }
            return form.checkValidity();
          })()`);
          assert.equal(ready, true, "New-password form must validate.");
          await clickVisible('main form button[type="submit"]');
          await waitForInteraction(
            '(() => location.pathname === "/accounts/reset/done/" && document.querySelector("main h1")?.textContent === "Password updated")()',
            "Reset POST must complete",
          );
          await cdp.send("Page.navigate", {url: resetLink});
          await waitForInteraction(
            '(() => document.querySelector("main h1")?.textContent === "Link expired")()',
            "Used reset token must not open another form",
          );
          // A real invalid-login POST must never authenticate, while a later
          // valid POST must establish only the new account workspace session.
          // The sign-out is a real CSRF-protected browser POST to Django.
          async function openNativeLogin() {
            await cdp.send("Page.navigate", {
              url: new URL("/accounts/start-sign-in/", draftPostOrigin).href,
            });
            await waitForInteraction(
              '(() => location.pathname === "/account/sign-in" && document.querySelector("main h1")?.textContent === "Sign in" && !!document.querySelector("main form[method=post]"))()',
              "Native sign-in must render after CSRF bootstrap",
            );
          }
          async function fillNativeLogin(password) {
            return cdp.js(`(() => {
              const form = document.querySelector("main form[method=post]");
              if (!form?.elements.namedItem("csrfmiddlewaretoken")?.value
                || form.elements.namedItem("native_login")?.value !== "1") return false;
              const name = form.elements.namedItem("username");
              const secret = form.elements.namedItem("password");
              if (!name || !secret) return false;
              name.value = "synthetic-browser-account";
              secret.value = ${JSON.stringify(password)};
              name.dispatchEvent(new Event("input", {bubbles: true}));
              secret.dispatchEvent(new Event("input", {bubbles: true}));
              return form.checkValidity();
            })()`);
          }
          await openNativeLogin();
          assert.equal(await fillNativeLogin("deliberately-incorrect-password"), true);
          await clickVisible('main form[method="post"] button[type="submit"]');
          await waitForInteraction(
            '(() => location.pathname === "/account/sign-in" && new URLSearchParams(location.search).get("notice") === "invalid" && !!document.querySelector("main [role=alert]"))()',
            "Wrong-password POST must show generic invalid notice",
          );
          await cdp.send("Page.navigate", {url: target.origin + "/dashboard"});
          await waitForInteraction(
            '(() => location.pathname === "/dashboard" && document.readyState === "complete" && !!document.querySelector("main h1"))()',
            "Wrong password must not grant a private dashboard",
          );
          const deniedContent = await cdp.js('document.querySelector("main")?.textContent || ""');
          for (const privateMarker of [
            "Synthetic signup workspace", "Foreign private marker", "Synthetic bakery",
          ]) {
            assert.equal(
              deniedContent.includes(privateMarker), false,
              "Invalid login revealed a private tenant marker",
            );
          }
          await openNativeLogin();
          assert.equal(await fillNativeLogin("Field#river75-polar%evergreen"), true);
          await clickVisible('main form[method="post"] button[type="submit"]');
          await waitForInteraction(
            '(() => location.pathname === "/dashboard" && document.querySelector("main h1")?.textContent === "Workspaces" && document.querySelector("main")?.textContent.includes("Synthetic signup workspace"))()',
            "Valid account login must reach its own workspace",
          );
          await inspectPrivate("/dashboard/workspaces/" + ownWorkspace,
            "Information unavailable",
            ["Synthetic signup workspace", "Foreign private marker", "Synthetic bakery"],
          );
          // The browser exercises a real authenticated password-change POST
          // after a rejected wrong-current-password attempt.
          await inspectPrivate("/dashboard", "Synthetic signup workspace", [
            "Foreign private marker", "Synthetic bakery",
          ]);
          const changeLink = await cdp.js(`document.querySelector('main a[href$="/accounts/password-change/"]')?.href || null`);
          assert.equal(changeLink, new URL("/accounts/password-change/", draftPostOrigin).href);
          const beforeChange = (await cdp.send("Network.getCookies", {
            urls: [target.origin, draftPostOrigin],
          })).cookies.find((cookie) => cookie.name === "sessionid")?.value;
          assert.ok(beforeChange, "Fixture browser must hold its own session.");
          await clickVisible('main a[href$="/accounts/password-change/"]');
          await waitForInteraction(
            '(() => location.pathname === "/accounts/password-change/" && document.querySelector("main h1")?.textContent === "Change your password")()',
            "Account link must open the CSRF-protected password form",
          );
          async function fillPasswordChange(current) {
            return cdp.js(`(() => {
              const form = document.querySelector("main form[method=post]");
              if (!form?.elements.namedItem("csrfmiddlewaretoken")?.value) return false;
              for (const [name, value] of Object.entries({
                old_password: ${JSON.stringify(current)},
                new_password1: "Synthetic-browser-updated-passphrase-1179",
                new_password2: "Synthetic-browser-updated-passphrase-1179",
              })) {
                const field = form.elements.namedItem(name);
                if (!field) return false;
                field.value = value;
                field.dispatchEvent(new Event("input", {bubbles: true}));
              }
              return form.checkValidity();
            })()`);
          }
          assert.equal(await fillPasswordChange("wrong-current-passphrase"), true);
          await clickVisible('main form[method="post"] button[type="submit"]');
          await waitForInteraction(
            '(() => location.pathname === "/accounts/password-change/" && document.querySelector("main")?.textContent.includes("Your old password was entered incorrectly"))()',
            "Wrong current password must be rejected",
          );
          assert.equal(await fillPasswordChange("Field#river75-polar%evergreen"), true);
          await clickVisible('main form[method="post"] button[type="submit"]');
          await waitForInteraction(
            '(() => location.pathname === "/accounts/password-change/done/" && document.querySelector("main h1")?.textContent === "Password updated")()',
            "New password must be saved through Django",
          );
          const afterChange = (await cdp.send("Network.getCookies", {
            urls: [target.origin, draftPostOrigin],
          })).cookies.find((cookie) => cookie.name === "sessionid")?.value;
          assert.ok(afterChange && afterChange !== beforeChange,
            "Password change must rotate and retain the active browser session.");
          await clickVisible('main a[href$="/dashboard"]');
          await waitForInteraction(
            '(() => location.pathname === "/dashboard" && document.querySelector("main")?.textContent.includes("Synthetic signup workspace"))()',
            "Password change must preserve the active account workspace",
          );
          await inspectPrivate("/dashboard/workspaces/" + ownWorkspace,
            "Information unavailable",
            ["Synthetic signup workspace", "Foreign private marker", "Synthetic bakery"],
          );
          console.log("PASS: browser change-password wrong-current rejection, successful update, session rotation and tenant isolation");
          await inspectPrivate("/account/sign-out", "End your session", [
            "Foreign private marker", "Synthetic bakery",
          ]);
          assert.equal(await cdp.js('(() => !!document.querySelector(\'main form[method="post"] input[name="csrfmiddlewaretoken"][value]\'))()'), true);
          await clickVisible('main form[method="post"] button[type="submit"]');
          await waitForInteraction(
            '(() => location.pathname === "/dashboard" && document.querySelector("main")?.textContent.includes("Sign in to see your workspaces."))()',
            "CSRF sign-out must remove the active browser session",
          );
          await inspectPrivate("/dashboard", "Sign in to see your workspaces.", [
            "Synthetic signup workspace", "Foreign private marker",
          ]);
          console.log("PASS: native browser invalid-login denial, own account login, foreign isolation and CSRF sign-out");
          console.log("PASS: browser recovery link, generic response, email token redemption and replay rejection");
        }
      }

      console.log(
        "PASS: 2 Chromium private viewports: anonymous/foreign/cookie deletion deny access; own workspace/job, read-only draft form, actual filter submit/Next/First links, source catalog and daily plans",
      );
    }
    // Fail closed if an anonymous page initiates ANY remote HTTP(S) or WS(S)
    // request. Loopback-only Next static assets are the sole network authority.
    const remotePublic = publicRequests.filter((url) => {
      if (!/^https?:|^wss?:/i.test(url)) return false;
      return new URL(url).origin !== target.origin;
    });
    assert.deepEqual(remotePublic, [], "Anonymous marketing must not contact external origins.");
    const localOrigins = new Set([
      target.origin,
      ...(draftPostOrigin ? [new URL(draftPostOrigin).origin] : []),
    ]);
    const remotePrivate = cdp.browserRequests.filter((url) => {
      if (!/^https?:|^wss?:/i.test(url)) return false;
      return !localOrigins.has(new URL(url).origin);
    });
    assert.deepEqual(remotePrivate, [], "Private browser contacted an unauthorized origin.");
    console.log(
      `PASS: ${viewports.length * paths.length} Chromium page/viewport checks; skip-link keyboard, FAQ click/focus, reduced motion, no overflow, 44px navigation/actions, zero external requests and no private markers; ${contrastSamples} text-contrast samples >=4.5:1; max ${peakRequests} first-party requests, ${(peakBytes / 1024 / 1024).toFixed(2)} MiB transfer`,
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
