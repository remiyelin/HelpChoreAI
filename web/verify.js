/* Checks a signed report in the viewer's own browser. No server is trusted.
   The signature covers payload_canonical byte for byte, so JSON is never re-canonicalised here. */
(function (root) {
  "use strict";
  const enc = new TextEncoder();
  const hexToBytes = (h) => Uint8Array.from((h.trim().match(/.{2}/g) || []).map((b) => parseInt(b, 16)));
  const toHex = (buf) => [...new Uint8Array(buf)].map((x) => x.toString(16).padStart(2, "0")).join("");
  const normalise = (t) => t.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

  async function sha256Hex(text) {
    return toHex(await root.crypto.subtle.digest("SHA-256", enc.encode(text)));
  }

  async function signatureState(pubHex, sigHex, signedText) {
    if (!root.crypto || !root.crypto.subtle) return "unsupported";
    let key;
    try {
      key = await root.crypto.subtle.importKey("raw", hexToBytes(pubHex), { name: "Ed25519" }, false, ["verify"]);
    } catch (e) {
      return "unsupported";
    }
    const ok = await root.crypto.subtle.verify({ name: "Ed25519" }, key, hexToBytes(sigHex), enc.encode(signedText));
    return ok ? "pass" : "fail";
  }

  /* Returns one state per check: pass, fail or unsupported. */
  async function checkReport(rep, pinnedHex, payloadText, reportText) {
    const out = { key: rep.public_key_hex.trim().toLowerCase() === pinnedHex.trim().toLowerCase() ? "pass" : "fail" };
    out.payload = await signatureState(pinnedHex, rep.signature_hex, payloadText);
    let parsed = null;
    try { parsed = JSON.parse(payloadText); } catch (e) { parsed = null; }
    out.report = parsed && (await sha256Hex(normalise(reportText))) === parsed.report_sha256 ? "pass" : "fail";
    out.parsed = parsed;
    return out;
  }

  const signed = (x) => (Object.is(x, -0) ? "-0.0000" : (x >= 0 ? "+" : "") + x.toFixed(4));  // same text as Python {:+.4f}

  /* The local rules that need no model. Mirrors checker.audit_report. */
  function localRules(text, payload, rules) {
    const low = text.toLowerCase(), errs = [];
    rules.banned.forEach((b) => { if (low.includes(b)) errs.push(`Banned phrase: "${b}"`); });
    if (!text.includes(rules.disclaimer)) errs.push("Disclaimer missing");
    if (payload) {
      [signed(payload.delta_raw), signed(payload.delta_adj), payload.rcv95.toFixed(4), payload.payload_sha256].forEach((t) => {
        if (!text.includes(t)) errs.push(`Signed value missing or changed: ${t.slice(0, 12)}`);
      });
    }
    return errs;
  }

  root.HCAVerify = { checkReport, localRules, sha256Hex, normalise };
})(typeof window !== "undefined" ? window : globalThis);
