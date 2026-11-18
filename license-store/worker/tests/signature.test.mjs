import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { signature } from "../dist/index.js";

const vectors = [
  ["SHA-256", "B66A92295697678D9A7C979DD4F6C48F8B3ECB7A74B1CC7C2A67741D39A630BD"],
  ["SHA-384", "F5AF79CB56BFE10F15B33F64262EB13BFCB1B49F3F54DD2E6F18D92C7ED7D8954C287F1D1B5AF99C45479139DF3612E7"],
  ["SHA-512", "88D5B1CE1C9B772F596AE4A8F641CF4D1DEEC4AFA18D300611BB53AFBFDA5AE6FC8460DFF26DACBB2333E7364A85EE5DADDE2BBB8EB6F39A6AF7B6BF4ACDFA3D"],
];

test("payment signature includes Shp_order after password #1", async () => {
  const value = "Merchant:100.00:12345:pass1:Shp_order=order-uuid";
  for (const [algorithm, expected] of vectors) {
    assert.equal(await signature(value, algorithm), expected);
  }
});

test("ResultURL signature follows OutSum:InvId:Password2:Shp_order", async () => {
  const value = "100.00:12345:pass2:Shp_order=order-uuid";
  const expected = createHash("sha256").update(value).digest("hex").toUpperCase();
  assert.equal(await signature(value, "SHA-256"), expected);
});

test("unsupported signature algorithms fail closed", async () => {
  await assert.rejects(() => signature("test", "MD5"), /Unsupported Robokassa hash algorithm/);
});
