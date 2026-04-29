/**
 * k6 Soak Test — Endurance at Stable Load
 * Focus: 100% write (create transaction) held at a fixed VU level for 30 minutes
 * Target: http://sense.ddns.net:8000
 *
 * Run AFTER k6_stress.js — set SOAK_VUS to ~80% of the VU count where stress test broke:
 *   SOAK_VUS=80 k6 run tests/k6_soak.js
 *   SOAK_VUS=80 k6 run tests/k6_soak.js --out json=soak_result.json
 *
 * If SOAK_VUS is not set, defaults to 50 VUs.
 *
 * What this measures:
 *   - Sustained TPS (transactions/sec) — use for cost-per-receipt formula
 *   - Memory leaks / performance degradation over time (latency should stay flat)
 *   - DB connection pool exhaustion under continuous load
 *
 * Cost formula after test:
 *   cost_per_receipt = server_cost_per_month / (stable_TPS × 86400 × 30)
 *
 * Thresholds (strict — test FAILS if these are breached):
 *   - http_req_failed < 1%
 *   - p(95) latency < 3000ms
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

const BASE_URL    = 'http://sense.ddns.net:8000';
const CREDENTIALS = { username: 'superadmin', password: 'admin1234' };
const SOAK_VUS    = parseInt(__ENV.SOAK_VUS, 10) || 50;

// Custom metrics
const writeLatency   = new Trend('write_latency', true);
const writeErrors    = new Rate('write_errors');
const receiptsCreated = new Counter('receipts_created');

export const options = {
  stages: [
    { duration: '2m',  target: SOAK_VUS }, // warm-up ramp
    { duration: '30m', target: SOAK_VUS }, // sustained soak
    { duration: '1m',  target: 0         }, // cool-down
  ],
  thresholds: {
    // Test fails (exit code 99) if either threshold is breached at any point
    'http_req_failed':                    ['rate<0.01'],   // < 1% error rate
    'http_req_duration{status:302}':      ['p(95)<3000'],  // 95th pct < 3s (successful creates)
    'write_errors':                       ['rate<0.01'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// ─── Setup: runs once ─────────────────────────────────────────────────────────
export function setup() {
  console.log(`[setup] SOAK_VUS = ${SOAK_VUS} (set via env: SOAK_VUS=<n> k6 run ...)`);

  const loginRes = http.post(`${BASE_URL}/web/login`, CREDENTIALS, { redirects: 5 });
  if (loginRes.status !== 200 && loginRes.status !== 302) {
    throw new Error(`Setup login failed: status ${loginRes.status}`);
  }

  const membersRes = http.get(`${BASE_URL}/web/members`);
  if (membersRes.status !== 200) {
    throw new Error(`Setup: GET /web/members failed: status ${membersRes.status}`);
  }

  // Extract member IDs from links: href="/web/members/{id}"
  const memberIds = [];
  const regex = /href="\/web\/members\/(\d+)"/g;
  let match;
  while ((match = regex.exec(membersRes.body)) !== null) {
    const id = parseInt(match[1], 10);
    if (!memberIds.includes(id)) memberIds.push(id);
  }

  // Auto-create a test member if none found
  if (memberIds.length === 0) {
    console.log('[setup] No members found — creating a test member automatically...');
    const enrollRes = http.post(
      `${BASE_URL}/web/enroll`,
      { name: 'k6-test-member', phone: '0800000001', tier: 'general' },
      { redirects: 5 }
    );
    if (enrollRes.status !== 200 && enrollRes.status !== 302) {
      throw new Error(`Setup: failed to create test member: status ${enrollRes.status}`);
    }
    // Extract ID from the final redirect URL: /web/members/{id}/new-bill
    const urlMatch = enrollRes.url.match(/\/web\/members\/(\d+)/);
    if (urlMatch) {
      memberIds.push(parseInt(urlMatch[1], 10));
    } else {
      throw new Error('Setup: could not extract member ID from enroll redirect. Check account permissions.');
    }
  }

  console.log(`[setup] Found ${memberIds.length} member(s): [${memberIds.join(', ')}]`);
  console.log(`[setup] Total test duration: ~33 minutes`);
  return { memberIds };
}

// ─── Per-VU state ─────────────────────────────────────────────────────────────
let loggedIn = false;

// ─── Default function ─────────────────────────────────────────────────────────
export default function (data) {
  // Login once per VU
  if (!loggedIn) {
    const loginRes = http.post(`${BASE_URL}/web/login`, CREDENTIALS, { redirects: 5 });
    const ok = check(loginRes, {
      'VU login ok': (r) => r.status === 200 || r.status === 302,
    });
    if (!ok) {
      writeErrors.add(1);
      sleep(1);
      return;
    }
    loggedIn = true;
  }

  // Pick a random member
  const memberId = data.memberIds[Math.floor(Math.random() * data.memberIds.length)];

  const itemsJson = JSON.stringify([{ name: 'SOAK_TEST', qty: 1, price: 100 }]);
  const res = http.post(
    `${BASE_URL}/web/members/${memberId}/new-bill`,
    {
      items_json: itemsJson,
      payment_method: 'cash',
      note: 'k6-soak',
    },
    { redirects: 0 }
  );

  writeLatency.add(res.timings.duration);

  const ok = check(res, {
    'create transaction: 302 redirect': (r) => r.status === 302,
    'create transaction: no server error': (r) => r.status < 500,
  });

  if (ok) {
    receiptsCreated.add(1);
  }
  writeErrors.add(ok ? 0 : 1);

  // Small think time — simulates realistic inter-request gap
  // Remove this line if you want maximum throughput measurement instead
  sleep(0.5);
}

// ─── Summary handler — print cost formula with actual numbers ─────────────────
export function handleSummary(data) {
  const totalDurationSec = 30 * 60; // soak phase only (30 min)
  const created = data.metrics.receipts_created
    ? data.metrics.receipts_created.values.count
    : 0;
  const stableTps   = created > 0 ? (created / totalDurationSec).toFixed(2) : 'N/A';
  const p95ms       = data.metrics.write_latency
    ? data.metrics.write_latency.values['p(95)'].toFixed(0)
    : 'N/A';
  const errorRate   = data.metrics.http_req_failed
    ? (data.metrics.http_req_failed.values.rate * 100).toFixed(2)
    : 'N/A';

  const summary = [
    '',
    '══════════════════════════════════════════════════',
    '  SOAK TEST SUMMARY',
    '══════════════════════════════════════════════════',
    `  VUs sustained          : ${SOAK_VUS}`,
    `  Receipts created       : ${created}`,
    `  Stable TPS (est.)      : ${stableTps} req/s`,
    `  p(95) write latency    : ${p95ms} ms`,
    `  Error rate             : ${errorRate}%`,
    '',
    '  COST FORMULA (fill in your server cost):',
    '  cost_per_receipt = server_cost_per_month ÷ (TPS × 86400 × 30)',
    `  Example @ 1,000 THB/mo : ${stableTps !== 'N/A' ? (1000 / (parseFloat(stableTps) * 86400 * 30)).toFixed(6) : 'N/A'} THB/receipt`,
    `  Example @ 3,000 THB/mo : ${stableTps !== 'N/A' ? (3000 / (parseFloat(stableTps) * 86400 * 30)).toFixed(6) : 'N/A'} THB/receipt`,
    `  Example @ 5,000 THB/mo : ${stableTps !== 'N/A' ? (5000 / (parseFloat(stableTps) * 86400 * 30)).toFixed(6) : 'N/A'} THB/receipt`,
    '══════════════════════════════════════════════════',
    '',
  ].join('\n');

  console.log(summary);

  // Return standard k6 summary (stdout) plus our custom lines
  return {
    stdout: summary,
  };
}
