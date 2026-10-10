import test from "node:test";
import assert from "node:assert/strict";
import { readBackend, trustedOrigin } from "../lib/transport.mjs";
const session = "a".repeat(32);
test("trusted origins reject credentials, paths and remote HTTP", () => {
  assert.equal(trustedOrigin("http://localhost:8000"), "http://localhost:8000");
  for (const value of [
    "http://example.com",
    "https://user:pass@example.com",
    "https://example.com/api",
    "https://example.com/?x=1",
  ])
    assert.throws(() => trustedOrigin(value));
});
test("missing and malformed sessions never contact backend", async () => {
  for (const value of [undefined, "a;other=secret", "bad"])
    assert.equal(
      (
        await readBackend(
          "http://localhost:8000",
          "/api/v1/workspaces/",
          value,
          () => {
            throw Error("must not fetch");
          },
        )
      ).kind,
      "signin",
    );
});
test("requests forward only session, disable cache and refuse redirects", async () => {
  const result = await readBackend(
    "http://localhost:8000",
    "/api/v1/workspaces/",
    session,
    async (url, options) => {
      assert.equal(url.href, "http://localhost:8000/api/v1/workspaces/");
      assert.deepEqual(options.headers, {
        Accept: "application/json",
        Cookie: `sessionid=${session}`,
      });
      assert.equal(options.cache, "no-store");
      assert.equal(options.redirect, "manual");
      return new Response('{"results":[]}', {
        headers: { "content-type": "application/json" },
      });
    },
  );
  assert.deepEqual(result, { kind: "ok", data: { results: [] } });
});
test("foreign origin paths rejected before request", async () => {
  for (const path of [
    "https://evil.example",
    "//evil.example/api",
    "/accounts/logout/",
    "/api/v1/workspaces/?page=1&target=https://evil.example",
  ])
    await assert.rejects(readBackend("http://localhost:8000", path, session));
});
test("denials, missing, redirect and backend failures stay generic", async () => {
  for (const [status, kind] of [
    [401, "denied"],
    [403, "denied"],
    [404, "missing"],
    [302, "unavailable"],
    [500, "unavailable"],
  ])
    assert.equal(
      (
        await readBackend(
          "http://localhost:8000",
          "/api/v1/workspaces/",
          session,
          async () => new Response("private details", { status }),
        )
      ).kind,
      kind,
    );
});
test("oversized and malformed JSON rejected", async () => {
  for (const body of ["x", '"' + "x".repeat(131073) + '"'])
    assert.equal(
      (
        await readBackend(
          "http://localhost:8000",
          "/api/v1/workspaces/",
          session,
          async () =>
            new Response(body, {
              headers: { "content-type": "application/json" },
            }),
        )
      ).kind,
      "unavailable",
    );
});
test("form paths require a bounded CSRF cookie and ordinary reads never forward it", async () => {
  const id =
    "a".repeat(8) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(12);
  const csrf = "B".repeat(32);
  for (const path of [
    "/api/v1/account/sign-out-form/",
    `/api/v1/workspaces/${id}/draft-form/`,
    `/api/v1/workspaces/${id}/draft-feedback/${id}/`,
    `/api/v1/workspaces/${id}/jobs/${id}/cancel-form/`,
    `/api/v1/workspaces/${id}/jobs/${id}/submit-form/`,
  ]) {
    for (const bad of [undefined, "bad", csrf + ";evil=1"])
      assert.equal(
        (
          await readBackend(
            "http://localhost:8000",
            path,
            session,
            () => {
              throw Error("must not fetch");
            },
            bad,
          )
        ).kind,
        "denied",
      );
    const result = await readBackend(
      "http://localhost:8000",
      path,
      session,
      async (_, options) => {
        assert.equal(
          options.headers.Cookie,
          `sessionid=${session}; csrftoken=${csrf}`,
        );
        assert.equal(options.cache, "no-store");
        return new Response("{}", {
          headers: { "content-type": "application/json" },
        });
      },
      csrf,
    );
    assert.equal(result.kind, "ok");
  }
  await readBackend(
    "http://localhost:8000",
    "/api/v1/workspaces/",
    session,
    async (_, options) => {
      assert.equal(options.headers.Cookie, `sessionid=${session}`);
      return new Response("{}", {
        headers: { "content-type": "application/json" },
      });
    },
    csrf,
  );
  await assert.rejects(
    readBackend(
      "http://localhost:8000",
      `/api/v1/workspaces/${id}/draft-form/?target=evil`,
      session,
    ),
  );
});
test("saved-job state filters stay on the exact job-list path", async () => {
  const id =
    "a".repeat(8) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(12);
  const path = `/api/v1/workspaces/${id}/jobs/?status=draft&after=${id}`;
  assert.equal(
    (
      await readBackend(
        "http://localhost:8000",
        path,
        session,
        async (_, options) => {
          assert.equal(options.headers.Cookie, `sessionid=${session}`);
          return new Response("{}", {
            headers: { "content-type": "application/json" },
          });
        },
      )
    ).kind,
    "ok",
  );
  for (const bad of [
    `/api/v1/workspaces/${id}/usage/?status=draft`,
    `/api/v1/workspaces/${id}/jobs/?status=evil`,
    `/api/v1/workspaces/${id}/jobs/?status=draft&target=evil`,
  ])
    await assert.rejects(readBackend("http://localhost:8000", bad, session));
});

test("anonymous login context forwards only bounded CSRF on one exact path", async () => {
  const path = "/api/v1/account/sign-in-form/";
  const csrf = "A".repeat(32);
  assert.equal(
    (
      await readBackend("http://localhost:8000", path, undefined, () => {
        throw Error("must not fetch");
      })
    ).kind,
    "denied",
  );
  for (const sessionValue of [undefined, session, "untrusted;cookie=1"]) {
    const result = await readBackend(
      "http://localhost:8000",
      path,
      sessionValue,
      async (_, options) => {
        assert.equal(options.headers.Cookie, `csrftoken=${csrf}`);
        assert.equal(options.cache, "no-store");
        assert.equal(options.redirect, "manual");
        return new Response("{}", {
          headers: { "content-type": "application/json" },
        });
      },
      csrf,
    );
    assert.equal(result.kind, "ok");
  }
  for (const other of [
    "/api/v1/account/sign-in-form/?next=/",
    "/api/v1/account/login/",
    "/api/v1/account/sign-in-form/../sign-out-form/",
  ]) {
    await assert.rejects(
      readBackend("http://localhost:8000", other, undefined, undefined, csrf),
      /Unsupported/,
    );
  }
  assert.equal(
    (
      await readBackend(
        "http://localhost:8000",
        "/api/v1/account/sign-out-form/",
        undefined,
        undefined,
        csrf,
      )
    ).kind,
    "signin",
  );
});

test("result snapshots require session and permit only exact bounded read paths", async () => {
  const path =
    "/api/v1/workspaces/11111111-1111-1111-1111-111111111111/jobs/22222222-2222-2222-2222-222222222222/results/";
  assert.equal(
    (await readBackend("http://localhost:8000", path)).kind,
    "signin",
  );
  const result = await readBackend(
    "http://localhost:8000",
    path,
    session,
    async (_, options) => {
      assert.equal(options.headers.Cookie, `sessionid=${session}`);
      assert.equal(options.cache, "no-store");
      return new Response("{}", {
        headers: { "content-type": "application/json" },
      });
    },
    "C".repeat(32),
  );
  assert.equal(result.kind, "ok");
  for (const bad of [
    path + "?country=GB",
    path + "?country=US&country=CA",
    path + "?after=x",
    path + "../accept/",
    path.replace("results", "accept"),
  ]) {
    await assert.rejects(
      readBackend("http://localhost:8000", bad, session),
      /Unsupported/,
    );
  }
});

test("export preview forwards validated form cookies only on exact path", async () => {
  const path = `/api/v1/workspaces/${"a".repeat(36)}/jobs/${"b".repeat(36)}/export-form/`;
  const csrf = "C".repeat(32);
  assert.equal(
    (await readBackend("http://localhost:8000", path, session)).kind,
    "denied",
  );
  const result = await readBackend(
    "http://localhost:8000",
    path,
    session,
    async (url, options) => {
      assert.equal(
        options.headers.Cookie,
        `sessionid=${session}; csrftoken=${csrf}`,
      );
      assert.equal(options.cache, "no-store");
      return new Response("{}", {
        headers: { "content-type": "application/json" },
      });
    },
    csrf,
  );
  assert.equal(result.kind, "ok");
  await assert.rejects(
    readBackend("http://localhost:8000", path + "?all=1", session),
  );
});

test("country filters permit only exact result and CSRF export-preview reads", async () => {
  const base = `/api/v1/workspaces/${"a".repeat(36)}/jobs/${"b".repeat(36)}/`;
  for (const suffix of ["results/?country=US", "export-form/?country=CA"]) {
    const result = await readBackend(
      "http://localhost:8000",
      base + suffix,
      session,
      async (_, options) => {
        assert.equal(
          options.headers.Cookie,
          `sessionid=${session}${suffix.startsWith("export") ? `; csrftoken=${"C".repeat(32)}` : ""}`,
        );
        assert.equal(options.cache, "no-store");
        return new Response("{}", {
          headers: { "content-type": "application/json" },
        });
      },
      "C".repeat(32),
    );
    assert.equal(result.kind, "ok");
  }
  for (const suffix of [
    "export-form/?country=GB",
    "cancel-form/?country=US",
    "results/?country=US&extra=x",
    "export-form/?country=CA&country=CA",
  ]) {
    await assert.rejects(
      readBackend("http://localhost:8000", base + suffix, session),
      /Unsupported/,
    );
  }
});

test("metadata filters use canonical bounded indices only on result and export-form paths", async () => {
  const base = `/api/v1/workspaces/${"a".repeat(36)}/jobs/${"b".repeat(36)}/`;
  for (const suffix of [
    "results/?category=0",
    "results/?source=11",
    "results/?country=CA&category=1&source=0",
    "export-form/?category=1&source=0",
    "export-form/?country=US&source=0",
  ]) {
    const result = await readBackend(
      "http://localhost:8000",
      base + suffix,
      session,
      async (_, options) => {
        assert.equal(
          options.headers.Cookie,
          `sessionid=${session}${suffix.startsWith("export") ? `; csrftoken=${"C".repeat(32)}` : ""}`,
        );
        assert.equal(options.cache, "no-store");
        return new Response("{}", {
          headers: { "content-type": "application/json" },
        });
      },
      "C".repeat(32),
    );
    assert.equal(result.kind, "ok");
  }
  for (const suffix of [
    "results/?category=12",
    "results/?category=01",
    "results/?category=software",
    "results/?source=fixture",
    "results/?source=-1",
    "results/?source=0&category=1",
    "results/?category=0&category=0",
    "results/?category=0?source=0",
    "results/?country=US&source=0&extra=1",
    "cancel-form/?category=0",
    "export-form/?source=12",
  ]) {
    await assert.rejects(
      readBackend("http://localhost:8000", base + suffix, session),
      /Unsupported/,
    );
  }
});

test("receipt history is readonly and forwards session only on exact bounded paths", async () => {
  const path = `/api/v1/workspaces/${"a".repeat(36)}/jobs/${"b".repeat(36)}/export-receipts/`;
  for (const suffix of ["", "?after=synthetic%3Acursor-signature"]) {
    const result = await readBackend(
      "http://localhost:8000",
      path + suffix,
      session,
      async (_, options) => {
        assert.equal(options.headers.Cookie, `sessionid=${session}`);
        assert.equal(options.cache, "no-store");
        return new Response("{}", {
          headers: { "content-type": "application/json" },
        });
      },
      "C".repeat(32),
    );
    assert.equal(result.kind, "ok");
  }
  for (const suffix of [
    "?page=1",
    "?after=x&after=y",
    "?after=" + "x".repeat(1201),
    "?after=x&all=1",
    "../exports/",
  ]) {
    await assert.rejects(
      readBackend("http://localhost:8000", path + suffix, session),
      /Unsupported/,
    );
  }
});

test("workspace members list is session-only, bounded and read-only", async () => {
  const id =
    "a".repeat(8) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(4) +
    "-" +
    "a".repeat(12);
  for (const path of [
    `/api/v1/workspaces/${id}/members/`,
    `/api/v1/workspaces/${id}/members/?page=2`,
  ]) {
    const result = await readBackend(
      "http://localhost:8000",
      path,
      session,
      async (_, options) => {
        assert.deepEqual(options.headers, {
          Accept: "application/json",
          Cookie: `sessionid=${session}`,
        });
        assert.equal(options.cache, "no-store");
        return new Response('{"count":0,"next":null,"results":[]}', {
          headers: { "content-type": "application/json" },
        });
      },
    );
    assert.equal(result.kind, "ok");
  }
  for (const path of [
    `/api/v1/workspaces/${id}/members/?page=0`,
    `/api/v1/workspaces/${id}/members/?page=-1`,
    `/api/v1/workspaces/${id}/members/?page=1&extra=1`,
    `/api/v1/workspaces/${id}/members/?after=${id}`,
    `/api/v1/workspaces/${id}/members/${id}/`,
  ]) {
    await assert.rejects(readBackend("http://localhost:8000", path, session));
  }
});

test("workspace identity route accepts only an exact session-bound GET path", async () => {
  const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const path = `/api/v1/workspaces/${id}/`;
  assert.equal(
    (
      await readBackend(
        "http://localhost:8000",
        path,
        session,
        async (_, options) => {
          assert.deepEqual(options.headers, {
            Accept: "application/json",
            Cookie: `sessionid=${session}`,
          });
          assert.equal(options.redirect, "manual");
          return new Response(
            '{"id":"' + id + '","name":"Example","timezone":"UTC"}',
            {
              headers: { "content-type": "application/json" },
            },
          );
        },
      )
    ).kind,
    "ok",
  );
  for (const bad of [
    `${path}?fields=secret`,
    `${path}../members/`,
    `${path}change/`,
    `/api/v1/workspaces/${id}/?page=1`,
  ]) {
    await assert.rejects(readBackend("http://localhost:8000", bad, session));
  }
  const anonymous = await readBackend(
    "http://localhost:8000",
    path,
    undefined,
    () => {
      throw Error("Anonymous lookup must not reach backend");
    },
  );
  assert.equal(anonymous.kind, "signin");
});

test("job summary uses a single exact session-only read and refuses query mutation", async () => {
  const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const path = `/api/v1/workspaces/${id}/job-summary/`;
  const response = await readBackend(
    "http://localhost:8000",
    path,
    session,
    async (url, options) => {
      assert.equal(url.pathname, path);
      assert.deepEqual(options.headers, {
        Accept: "application/json",
        Cookie: `sessionid=${session}`,
      });
      assert.equal(options.cache, "no-store");
      assert.equal(options.redirect, "manual");
      return new Response(
        '{"workspace_id":"' + id + '","total":0,"statuses":{}}',
        {
          headers: { "content-type": "application/json" },
        },
      );
    },
  );
  assert.equal(response.kind, "ok");
  for (const invalid of [
    `${path}?status=completed`,
    `${path}?page=2`,
    `${path}?target=https://evil.example`,
    `${path}../jobs/`,
  ]) {
    await assert.rejects(
      readBackend("http://localhost:8000", invalid, session),
    );
  }
  const anonymous = await readBackend(
    "http://localhost:8000",
    path,
    undefined,
    () => {
      throw new Error("An anonymous summary must not reach Django");
    },
  );
  assert.equal(anonymous.kind, "signin");
});

test("daily plans list is exact, session-only and rejects arbitrary paths", async () => {
  const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const cursor = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
  const root = `/api/v1/workspaces/${id}/daily-plans/`;
  for (const path of [root, `${root}?after=${cursor}`]) {
    const result = await readBackend(
      "http://localhost:8000",
      path,
      session,
      async (url, options) => {
        assert.equal(url.pathname + url.search, path);
        assert.deepEqual(options.headers, {
          Accept: "application/json",
          Cookie: `sessionid=${session}`,
        });
        assert.equal(options.cache, "no-store");
        assert.equal(options.redirect, "manual");
        return new Response(
          `{"workspace_id":"${id}","total":0,"results":[],"next":null}`,
          { headers: { "content-type": "application/json" } },
        );
      },
    );
    assert.equal(result.kind, "ok");
  }
  for (const bad of [
    `${root}?page=1`,
    `${root}?after=invalid`,
    `${root}?after=${cursor}&status=disabled`,
    `${root}../members/`,
  ]) {
    await assert.rejects(readBackend("http://localhost:8000", bad, session));
  }
  const anonymous = await readBackend(
    "http://localhost:8000",
    root,
    undefined,
    () => {
      throw new Error("Anonymous daily plan list reached the backend");
    },
  );
  assert.equal(anonymous.kind, "signin");
});

test("daily plan detail allows exact session GET and refuses activation or query paths", async () => {
  const workspaceId = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const planId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
  const path = `/api/v1/workspaces/${workspaceId}/daily-plans/${planId}/`;
  const result = await readBackend(
    "http://localhost:8000",
    path,
    session,
    async (url, options) => {
      assert.equal(url.pathname, path);
      assert.deepEqual(options.headers, {
        Accept: "application/json",
        Cookie: `sessionid=${session}`,
      });
      assert.equal(options.cache, "no-store");
      assert.equal(options.redirect, "manual");
      return new Response(
        '{"id":"' + planId + '","workspace_id":"' + workspaceId + '"}',
        {
          headers: { "content-type": "application/json" },
        },
      );
    },
  );
  assert.equal(result.kind, "ok");
  for (const invalid of [
    `${path}?activate=1`,
    `${path}?fields=secret`,
    `${path}../`,
    `/api/v1/workspaces/${workspaceId}/daily-plans/${planId}/activate/`,
  ]) {
    await assert.rejects(
      readBackend("http://localhost:8000", invalid, session),
    );
  }
  const anonymous = await readBackend(
    "http://localhost:8000",
    path,
    undefined,
    () => {
      throw Error("Anonymous plan-detail lookup must not reach Django");
    },
  );
  assert.equal(anonymous.kind, "signin");
});

test("daily diagnostics path is a fixed authenticated read-only URL", async () => {
  const id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const cursor = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
  const root = `/api/v1/workspaces/${id}/daily-diagnostics/`;
  for (const path of [root, `${root}?after=${cursor}`]) {
    const result = await readBackend(
      "http://localhost:8000",
      path,
      session,
      async (url, options) => {
        assert.equal(url.pathname + url.search, path);
        assert.deepEqual(options.headers, {
          Accept: "application/json",
          Cookie: `sessionid=${session}`,
        });
        assert.equal(options.cache, "no-store");
        assert.equal(options.redirect, "manual");
        return new Response(
          `{"workspace_id":"${id}","advisory_only":true,"total_plans":0,"inspected":0,"plans":[]}`,
          { headers: { "content-type": "application/json" } },
        );
      },
    );
    assert.equal(result.kind, "ok");
  }
  for (const path of [
    `${root}?page=2`,
    `${root}?limit=999`,
    `${root}?after=bad`,
    `${root}?after=${cursor}&activate=true`,
    `${root}../daily-plans/`,
    `${root}run/`,
  ]) {
    await assert.rejects(readBackend("http://localhost:8000", path, session));
  }
  const anonymous = await readBackend(
    "http://localhost:8000",
    root,
    undefined,
    () => { throw Error("Anonymous diagnostics cannot reach Django"); },
  );
  assert.equal(anonymous.kind, "signin");
});
