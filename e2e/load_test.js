import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<30000'], // 95% of requests must complete below 30s
  },
};

const BASE_URL = 'http://localhost:8000/api/v1';


export default function () {
  const headers = {
    'Authorization': 'Bearer e2e-token',
    'Content-Type': 'application/json',
  };

  // 1. Mock statement upload
  const uploadRes = http.post(`${BASE_URL}/statements/upload`, JSON.stringify({
    bank: 'hdfc',
    pages: 100
  }), { headers });
  
  check(uploadRes, {
    'upload status is 200': (r) => r.status === 200,
  });

  const statementId = uploadRes.json('data.id');
  if (!statementId) return;

  // 2. Poll parsing status until ready
  let status = 'PARSING';
  let attempts = 0;
  
  while (status === 'PARSING' && attempts < 15) {
    sleep(2);
    const statusRes = http.get(`${BASE_URL}/statements/${statementId}/status`, { headers });
    check(statusRes, { 'status status is 200': (r) => r.status === 200 });
    status = statusRes.json('data.status');
    attempts++;
  }

  // 3. Export transactions
  const exportRes = http.post(`${BASE_URL}/statements/${statementId}/export`, JSON.stringify({
    format: 'csv'
  }), { headers });

  check(exportRes, {
    'export trigger status is 200': (r) => r.status === 200,
  });
}
