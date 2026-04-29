/**
 * k6 Stress Test — Find Breaking Point
 * Focus: 100% write (create transaction)
 * Target: http://sense.ddns.net:8000
 *
 * Run:
 *   k6 run tests/k6_stress.js
 *   k6 run tests/k6_stress.js --out json=stress_result.json
 *
 * Reading results:
 *   - http_reqs rate       → TPS (req/s) at each stage
 *   - checks               → success rate — watch for stage where it drops below 95%
 *   - http_req_failed rate → error rate — breaking point = stage where this spikes > 5%
 *   - http_req_duration p(95) → latency degradation
 *   - dropped_iterations   → VUs couldn't keep up (server saturated)
 *
 * After test: set SOAK_VUS = ~80% of VU count at breaking stage, then run k6_soak.js
 */

import http from 'k6/http';
import { check } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE_URL = 'http://sense.ddns.net:8000';
const CREDENTIALS = { username: 'superadmin', password: 'admin1234' };

// Custom metrics — broken out per phase for easier analysis
const writeLatency = new Trend('write_latency', true);
const writeErrors  = new Rate('write_errors');

export const options = {
  // Ramp VUs from 1 → 200, then cool down
  // Each stage is 30s so it's easy to correlate stage → VU count in the summary
  stages: [
    { duration: '30s', target: 1   },  // baseline
    { duration: '30s', target: 5   },
    { duration: '30s', target: 10  },
    { duration: '30s', target: 20  },
    { duration: '30s', target: 50  },
    { duration: '30s', target: 100 },
    { duration: '30s', target: 150 },
    { duration: '30s', target: 200 },
    { duration: '15s', target: 0   },  // cool-down
  ],
  // No thresholds intentionally — we want to observe the natural error curve,
  // not abort early. Watch the output as the test runs.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// ─── Setup: runs once, returns test data for all VUs ─────────────────────────
export function setup() {
  // Login with setup VU's own cookie jar
  const loginRes = http.post(`${BASE_URL}/web/login`, CREDENTIALS, {
    redirects: 5,
  });
  if (loginRes.status !== 200 && loginRes.status !== 302) {
    throw new Error(`Setup login failed: status ${loginRes.status}`);
  }

  // Fetch members list — cookie is in setup VU's jar automatically
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
  return { memberIds };
}

// ─── Per-VU state (each VU has its own JS runtime, so this is isolated) ──────
let loggedIn = false;

// ─── Default function: runs repeatedly for each VU ───────────────────────────
export default function (data) {
  // Login once per VU lifetime — cookie persists in this VU's jar for all iterations
  if (!loggedIn) {
    const loginRes = http.post(`${BASE_URL}/web/login`, CREDENTIALS, {
      redirects: 5,
    });
    const ok = check(loginRes, {
      'VU login ok': (r) => r.status === 200 || r.status === 302,
    });
    if (!ok) {
      writeErrors.add(1);
      return; // skip this iteration if login failed
    }
    loggedIn = true;
  }

  // Pick a random member from the pool returned by setup()
  const memberId = data.memberIds[Math.floor(Math.random() * data.memberIds.length)];

  // POST create transaction — don't follow redirect so we see the raw 302
  const itemsJson = JSON.stringify([{ name: 'LOAD_TEST', qty: 1, price: 100 }]);
  const res = http.post(
    `${BASE_URL}/web/members/${memberId}/new-bill`,
    {
      items_json: itemsJson,
      payment_method: 'cash',
      note: 'k6-stress',
    },
    { redirects: 0 } // 302 = success (redirect to receipt page)
  );

  writeLatency.add(res.timings.duration);

  const ok = check(res, {
    'create transaction: 302 redirect': (r) => r.status === 302,
    'create transaction: no server error': (r) => r.status < 500,
  });

  writeErrors.add(ok ? 0 : 1);
}
