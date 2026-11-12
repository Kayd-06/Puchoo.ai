import assert from "node:assert/strict";
import test from "node:test";
import { backendPort, backendTarget } from "./dev-config.mjs";

test("uses a dedicated port for the Puchoo API", () => {
  assert.equal(backendPort({}), 8001);
  assert.equal(backendTarget({}), "http://127.0.0.1:8001");
});
test("keeps the backend launcher and frontend target on the configured port", () => {
  const env = { PUCHOO_API_PORT: "8012" };
  assert.equal(backendPort(env), 8012);
  assert.equal(backendTarget(env), "http://127.0.0.1:8012");
});
test("rejects invalid ports before starting the development servers", () => {
  for (const value of ["0", "65536", "abc", "8001/path", "3.5"]) {
    assert.throws(
      () => backendPort({ PUCHOO_API_PORT: value }),
      /PUCHOO_API_PORT/,
    );
  }
});
