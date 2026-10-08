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
