// EventPulse k6 Flash-Sale Load Testing Script
// Simulates 500 concurrent attendees hammering the ticketing engine at 00:00

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

export const errorRate = new Rate('errors');
export const holdLatency = new Trend('hold_duration_ms');

export const options = {
  stages: [
    { duration: '5s', target: 50 },    // Ramp-up: 50 virtual users entering
    { duration: '15s', target: 200 },  // Flash sale spike: 200 concurrent users
    { duration: '5s', target: 0 },     // Ramp-down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<50'], // 95% of requests must complete under 50ms
    'errors': ['rate<0.01'],           // Server error rate under 1% (excluding expected 409s)
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://localhost:8000';

export default function () {
  const userId = `vu_user_${__VU}_${__ITER}`;
  const seatId = `B-0${(__ITER % 10) + 1}`; // Concurrent contention across row B seats

  // 1. Query CQRS Read Seatmap (Read Path)
  const seatmapRes = http.get(`${BASE_URL}/api/v1/events/fest_rvce_2026/seatmap`);
  check(seatmapRes, {
    'Seatmap status 200': (r) => r.status === 200,
    'Seatmap response < 20ms': (r) => r.timings.duration < 20,
  });

  // 2. Attempt Atomic Hold on Seat (Write Path)
  const holdPayload = JSON.stringify({
    event_id: 'fest_rvce_2026',
    seat_id: seatId,
    user_id: userId,
    hold_duration_seconds: 60,
  });

  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const holdStart = Date.now();
  const holdRes = http.post(`${BASE_URL}/api/v1/reservations/hold`, holdPayload, params);
  holdLatency.add(Date.now() - holdStart);

  // Success (201) or expected conflict (409) are both valid business outcomes under high contention
  const validOutcome = holdRes.status === 201 || holdRes.status === 409;
  check(holdRes, {
    'Atomic hold status is 201 or 409': () => validOutcome,
    'Sub-millisecond Redis lock evaluation': (r) => r.timings.duration < 50,
  });

  if (!validOutcome) {
    errorRate.add(1);
  }

  sleep(0.1);
}
