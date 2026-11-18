interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  PUBLIC_BASE_URL: string;
  ROBOKASSA_URL: string;
  ROBOKASSA_HASH_ALGORITHM: string;
  CURRENCY: string;
  ROBOKASSA_MERCHANT_LOGIN?: string;
  ROBOKASSA_PASSWORD_1?: string;
  ROBOKASSA_PASSWORD_2?: string;
  LICENSE_ENCRYPTION_KEY?: string;
  RESEND_API_KEY?: string;
  LICENSE_MAIL_FROM?: string;
}

type Plan = {
  id: string; title: string; description: string; amount_minor: number;
  currency: string; duration_days: number | null; is_active: number;
};

const json = (data: unknown, status = 200, headers: HeadersInit = {}) =>
  new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers } });

const text = (body: string, status = 200) => new Response(body, { status, headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });

function cors(request: Request): HeadersInit {
  const origin = request.headers.get("Origin");
  const allowed = origin && /^https:\/\/[a-z0-9-]+\.workers\.dev$/i.test(origin) ? origin : "";
  return {
    ...(allowed ? { "access-control-allow-origin": allowed, "vary": "Origin" } : {}),
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "Content-Type",
    "access-control-max-age": "86400",
  };
}

function money(minor: number): string {
  return (minor / 100).toFixed(2);
}

function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function encryptLicense(value: string, secret: string): Promise<string> {
  const raw = Uint8Array.from(atob(secret), c => c.charCodeAt(0));
  if (raw.length !== 32) throw new Error("LICENSE_ENCRYPTION_KEY must be base64-encoded 32 bytes");
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(value)));
  const packed = new Uint8Array(iv.length + ciphertext.length);
  packed.set(iv, 0);
  packed.set(ciphertext, iv.length);
  return btoa(String.fromCharCode(...packed));
}

async function sha256(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, "0")).join("");
}

export async function signature(value: string, algorithm: string): Promise<string> {
  const normalized = algorithm.trim().toUpperCase().replace("_", "-");
  if (!["SHA-256", "SHA-384", "SHA-512"].includes(normalized)) {
    throw new Error("Unsupported Robokassa hash algorithm");
  }
  const digest = await crypto.subtle.digest(normalized, new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, "0")).join("").toUpperCase();
}

async function decryptLicense(value: string, secret: string): Promise<string> {
  const raw = Uint8Array.from(atob(secret), c => c.charCodeAt(0));
  if (raw.length !== 32) throw new Error("LICENSE_ENCRYPTION_KEY must be base64-encoded 32 bytes");
  const packed = Uint8Array.from(atob(value), c => c.charCodeAt(0));
  if (packed.length < 29) throw new Error("Invalid encrypted license payload");
  const key = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: packed.slice(0, 12) }, key, packed.slice(12));
  return new TextDecoder().decode(plain);
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>\"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '\"': "&quot;", "'": "&#39;" }[ch] || ch));
}

async function deliverPendingEmails(env: Env, limit = 10): Promise<void> {
  if (!env.RESEND_API_KEY || !env.LICENSE_MAIL_FROM || !env.LICENSE_ENCRYPTION_KEY) return;
  const { results } = await env.DB.prepare("SELECT o.id AS order_id,o.email,p.title AS plan_title,l.encrypted_key,l.id AS license_id FROM email_outbox e JOIN orders o ON o.id=e.order_id JOIN licenses l ON l.id=e.license_id JOIN plans p ON p.id=l.plan_id WHERE e.status='pending' AND e.next_attempt_at<=CURRENT_TIMESTAMP ORDER BY e.created_at LIMIT ?").bind(limit).all<{order_id:string;email:string;plan_title:string;encrypted_key:string;license_id:string}>();
  for (const row of results) {
    const claimed = await env.DB.prepare("UPDATE email_outbox SET status='sending',attempts=attempts+1 WHERE order_id=? AND status='pending'").bind(row.order_id).run();
    if (!claimed.meta.changes) continue;
    try {
      const license = await decryptLicense(row.encrypted_key, env.LICENSE_ENCRYPTION_KEY);
      const html = '<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#172033"><h2>Лицензия Vkus</h2><p>Тариф: <b>' + escapeHtml(row.plan_title) + '</b></p><p>Ваш ключ лицензии:</p><div style="padding:16px;background:#101a32;color:#fff;font-size:20px;letter-spacing:1px;border-radius:8px">' + escapeHtml(license) + '</div><p>Введите ключ в приложении Vkus. Сохраните это письмо.</p><p style="color:#667085">Заказ: ' + escapeHtml(row.order_id) + '</p></div>';
      const response = await fetch("https://api.resend.com/emails", { method: "POST", headers: { "Authorization": "Bearer " + env.RESEND_API_KEY, "Content-Type": "application/json" }, body: JSON.stringify({ from: env.LICENSE_MAIL_FROM, to: [row.email], subject: "Ваш ключ лицензии Vkus", html }) });
      if (!response.ok) throw new Error("Resend HTTP " + response.status);
      await env.DB.prepare("UPDATE email_outbox SET status='sent',sent_at=CURRENT_TIMESTAMP,last_error=NULL WHERE order_id=?").bind(row.order_id).run();
      await env.DB.prepare("UPDATE licenses SET delivery_status='sent' WHERE id=?").bind(row.license_id).run();
    } catch (error) {
      const message = error instanceof Error ? error.message.slice(0, 240) : "mail_delivery_failed";
      await env.DB.prepare("UPDATE email_outbox SET status=CASE WHEN attempts>=8 THEN 'failed' ELSE 'pending' END,next_attempt_at=datetime('now', '+' || MIN(3600, (30 * (1 << MIN(attempts,7)))) || ' seconds'),last_error=? WHERE order_id=?").bind(message,row.order_id).run();
      await env.DB.prepare("UPDATE licenses SET delivery_status='failed' WHERE id=? AND (SELECT status FROM email_outbox WHERE order_id=?)='failed'").bind(row.license_id,row.order_id).run();
    }
  }
}

function makeLicenseKey(): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(20));
  const groups: string[] = [];
  for (let i = 0; i < bytes.length; i += 5) {
    groups.push([...bytes.slice(i, i + 5)].map(b => alphabet[b % alphabet.length]).join(""));
  }
  return "VK-" + groups.join("-");
}

function formValue(form: URLSearchParams, key: string): string {
  return form.get(key)?.trim() ?? "";
}

async function createOrder(request: Request, env: Env): Promise<Response> {
  const body = await request.json().catch(() => null) as { plan_id?: unknown; email?: unknown } | null;
  if (!body || typeof body.plan_id !== "string" || typeof body.email !== "string") return json({ error: "invalid_request" }, 400);
  const planId = body.plan_id.trim();
  const email = body.email.trim().toLowerCase();
  if (!/^[a-z0-9._%+-]{1,64}@[a-z0-9.-]+\.[a-z]{2,}$/i.test(email) || email.length > 254) return json({ error: "invalid_email" }, 400);
  if (!/^[a-z0-9_-]{1,48}$/i.test(planId)) return json({ error: "invalid_plan" }, 400);

  const plan = await env.DB.prepare("SELECT id,title,description,amount_minor,currency,duration_days,is_active FROM plans WHERE id=? AND is_active=1").bind(planId).first<Plan>();
  if (!plan) return json({ error: "plan_unavailable" }, 404);
  if (!env.ROBOKASSA_MERCHANT_LOGIN || !env.ROBOKASSA_PASSWORD_1 || !env.PUBLIC_BASE_URL || env.PUBLIC_BASE_URL.includes("REPLACE_")) return json({ error: "payments_not_configured" }, 503);

  const orderId = crypto.randomUUID();
  const amount = money(plan.amount_minor);
  const invId = String(Date.now()) + String(crypto.getRandomValues(new Uint16Array(1))[0]).padStart(5, "0");
  await env.DB.prepare("INSERT INTO orders (id,plan_id,email,amount_minor,currency,status,robokassa_inv_id) VALUES (?,?,?,?,?,'pending',?)")
    .bind(orderId, plan.id, email, plan.amount_minor, plan.currency, invId).run();

  const sign = await signature(`${env.ROBOKASSA_MERCHANT_LOGIN}:${amount}:${invId}:${env.ROBOKASSA_PASSWORD_1}:Shp_order=${orderId}`, env.ROBOKASSA_HASH_ALGORITHM || "SHA-256");
  const url = new URL(env.ROBOKASSA_URL);
  url.searchParams.set("MerchantLogin", env.ROBOKASSA_MERCHANT_LOGIN);
  url.searchParams.set("OutSum", amount);
  url.searchParams.set("InvId", invId);
  url.searchParams.set("Description", `Vkus license: ${plan.title}`);
  url.searchParams.set("SignatureValue", sign);
  url.searchParams.set("Culture", "ru");
  url.searchParams.set("Encoding", "utf-8");
  url.searchParams.set("Email", email);
  url.searchParams.set("IsTest", "1");
  url.searchParams.set("Shp_order", orderId);
  return json({ order_id: orderId, payment_url: url.toString(), status: "pending" }, 201);
}

async function robokassaResult(request: Request, env: Env): Promise<Response> {
  if (!env.ROBOKASSA_PASSWORD_2 || !env.LICENSE_ENCRYPTION_KEY) return text("CONFIG_ERROR", 503);
  const raw = await request.text();
  const form = new URLSearchParams(raw);
  const outSum = formValue(form, "OutSum");
  const invId = formValue(form, "InvId");
  const supplied = formValue(form, "SignatureValue").toUpperCase();
  const orderId = formValue(form, "Shp_order");
  if (!outSum || !invId || !supplied || !orderId) return text("BAD_REQUEST", 400);

  const expected = await signature(`${outSum}:${invId}:${env.ROBOKASSA_PASSWORD_2}:Shp_order=${orderId}`, env.ROBOKASSA_HASH_ALGORITHM || "SHA-256");
  if (!safeEqual(supplied, expected)) return text("BAD_SIGNATURE", 403);

  const order = await env.DB.prepare("SELECT id,amount_minor,status,robokassa_inv_id FROM orders WHERE id=?").bind(orderId).first<{id:string;amount_minor:number;status:string;robokassa_inv_id:string}>();
  if (!order || order.robokassa_inv_id !== invId || money(order.amount_minor) !== Number(outSum).toFixed(2)) return text("ORDER_MISMATCH", 409);
  const eventHash = await sha256(raw);
  const eventKey = `robokassa:${invId}:${supplied}`;
  const existing = await env.DB.prepare("SELECT id FROM payment_events WHERE event_key=?").bind(eventKey).first();
  if (existing || order.status === "paid") return text(`OK${invId}`);

  const licenseKey = makeLicenseKey();
  const keyHash = await sha256(licenseKey);
  const encryptedKey = await encryptLicense(licenseKey, env.LICENSE_ENCRYPTION_KEY);
  const licenseId = crypto.randomUUID();
  const plan = await env.DB.prepare("SELECT duration_days FROM plans WHERE id=(SELECT plan_id FROM orders WHERE id=?)").bind(orderId).first<{duration_days:number|null}>();
  const expiresAt = plan?.duration_days ? new Date(Date.now() + plan.duration_days * 86400000).toISOString() : null;

  try {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO payment_events (order_id,provider,event_key,payload_sha256) VALUES (?,'robokassa',?,?)").bind(orderId,eventKey,eventHash),
      env.DB.prepare("UPDATE orders SET status='paid',paid_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'").bind(orderId),
      env.DB.prepare("INSERT INTO licenses (id,order_id,plan_id,key_hash,encrypted_key,key_hint,status,expires_at) SELECT ?,id,plan_id,?,?,?, 'active',? FROM orders WHERE id=?").bind(licenseId,keyHash,encryptedKey,licenseKey.slice(-5),expiresAt,orderId),
      env.DB.prepare("INSERT INTO email_outbox (order_id,license_id,status) VALUES (?,?,'pending')").bind(orderId,licenseId),
    ]);
  } catch {
    return text("TEMPORARY_DB_ERROR", 503);
  }
  return text(`OK${invId}`);
}

async function activate(request: Request, env: Env): Promise<Response> {
  const body = await request.json().catch(() => null) as { license_key?: unknown; installation_id?: unknown; app_version?: unknown } | null;
  if (!body || typeof body.license_key !== "string" || typeof body.installation_id !== "string") return json({ error: "invalid_request" }, 400);
  const key = body.license_key.trim().toUpperCase();
  const installation = body.installation_id.trim();
  if (!/^VK-(?:[A-HJ-NP-Z2-9]{5}-){3}[A-HJ-NP-Z2-9]{5}$/.test(key) || !/^[a-zA-Z0-9._:-]{8,128}$/.test(installation)) return json({ error: "invalid_credentials" }, 400);
  const keyHash = await sha256(key);
  const license = await env.DB.prepare("SELECT id,plan_id,status,expires_at FROM licenses WHERE key_hash=?").bind(keyHash).first<{id:string;plan_id:string;status:string;expires_at:string|null}>();
  if (!license || license.status !== "active" || (license.expires_at && Date.parse(license.expires_at) < Date.now())) return json({ error: "license_invalid" }, 403);
  await env.DB.prepare("INSERT INTO activations (license_id,installation_id,app_version) VALUES (?,?,?) ON CONFLICT(license_id,installation_id) DO UPDATE SET last_seen_at=CURRENT_TIMESTAMP,app_version=excluded.app_version")
    .bind(license.id, installation, typeof body.app_version === "string" ? body.app_version.slice(0,32) : null).run();
  return json({ active: true, plan_id: license.plan_id, expires_at: license.expires_at });
}

export default {
  async scheduled(_event: ScheduledController, env: Env, ctx: ExecutionContext) { ctx.waitUntil(deliverPendingEmails(env)); },
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(request) });
    let response: Response;
    try {
      if (url.pathname === "/api/health" && request.method === "GET") response = json({ ok: true, service: "vkus-license-store", payments_configured: Boolean(env.ROBOKASSA_MERCHANT_LOGIN && env.ROBOKASSA_PASSWORD_1 && env.ROBOKASSA_PASSWORD_2) });
      else if (url.pathname === "/api/plans" && request.method === "GET") {
        const { results } = await env.DB.prepare("SELECT id,title,description,amount_minor,currency,duration_days FROM plans WHERE is_active=1 ORDER BY amount_minor").all();
        response = json({ plans: results });
      } else if (url.pathname === "/api/orders" && request.method === "POST") response = await createOrder(request, env);
      else if (url.pathname === "/robokassa/result" && request.method === "POST") response = await robokassaResult(request, env);
      else if (url.pathname === "/api/licenses/activate" && request.method === "POST") response = await activate(request, env);
      else if (url.pathname === "/robokassa/success" && request.method === "GET") response = text("Платёж отправлен на проверку. Вернитесь в Vkus и обновите статус заказа.");
      else if (url.pathname === "/robokassa/fail" && request.method === "GET") response = text("Оплата не завершена. Заказ сохранён, лицензия не выдана.");
      else if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/robokassa/")) response = json({ error: "not_found" }, 404);
      else response = await env.ASSETS.fetch(request);
    } catch {
      response = json({ error: "service_unavailable" }, 503);
    }
    const headers = new Headers(response.headers);
    for (const [key, value] of Object.entries(cors(request))) headers.set(key, value);
    headers.set("x-content-type-options", "nosniff");
    headers.set("referrer-policy", "no-referrer");
    headers.set("x-frame-options", "DENY");
    headers.set("content-security-policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'self'");
    return new Response(response.body, { status: response.status, headers });
  },
};
