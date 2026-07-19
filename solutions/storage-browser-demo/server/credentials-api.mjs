/**
 * Local credentials API server for Storage Browser demo.
 *
 * Provides temporary AWS credentials to the frontend via /api/credentials.
 * Uses the AWS SDK credential chain (env vars, ~/.aws/credentials, IAM role).
 *
 * Usage:
 *   node server/credentials-api.mjs
 *
 * The Vite dev server proxies /api/credentials to this server (port 3001).
 *
 * SECURITY NOTE:
 * - This is for LOCAL DEVELOPMENT ONLY.
 * - Never expose this endpoint to the internet.
 * - For production, use Cognito Identity Pool or API Gateway + Lambda.
 */
import { createServer } from 'http';
import { fromNodeProviderChain } from '@aws-sdk/credential-providers';

const PORT = 3001;
const credentialProvider = fromNodeProviderChain({ clientConfig: { region: 'ap-northeast-1' } });

const server = createServer(async (req, res) => {
  // CORS headers for Vite dev server
  res.setHeader('Access-Control-Allow-Origin', 'http://localhost:5173');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.url === '/api/credentials' && req.method === 'GET') {
    try {
      const credentials = await credentialProvider();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        accessKeyId: credentials.accessKeyId,
        secretAccessKey: credentials.secretAccessKey,
        sessionToken: credentials.sessionToken || '',
        expiration: credentials.expiration?.toISOString() || new Date(Date.now() + 3600000).toISOString(),
      }));
    } catch (err) {
      console.error('Credential error:', err.message);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
  } else {
    res.writeHead(404);
    res.end('Not found');
  }
});

server.listen(PORT, () => {
  console.log(`Credentials API running on http://localhost:${PORT}/api/credentials`);
  console.log('This provides AWS credentials to the Storage Browser frontend.');
  console.log('Press Ctrl+C to stop.');
});
