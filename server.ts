import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { createServer as createViteServer } from 'vite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;
const FASTAPI_TARGET = process.env.FASTAPI_TARGET || 'http://127.0.0.1:8000';

app.use(express.json());

// Proxy /api requests to FastAPI backend
app.use('/api', async (req, res) => {
  try {
    const targetUrl = `${FASTAPI_TARGET}${req.originalUrl}`;
    const headers: Record<string, string> = {
      'content-type': req.headers['content-type'] || 'application/json',
    };
    if (req.headers.authorization) {
      headers['authorization'] = req.headers.authorization;
    }

    const fetchOptions: RequestInit = {
      method: req.method,
      headers,
    };

    if (['POST', 'PUT', 'PATCH'].includes(req.method) && Object.keys(req.body || {}).length > 0) {
      fetchOptions.body = JSON.stringify(req.body);
    }

    const response = await fetch(targetUrl, fetchOptions);
    const contentType = response.headers.get('content-type') || '';

    res.status(response.status);
    if (contentType.includes('application/json')) {
      const data = await response.json();
      return res.json(data);
    } else {
      const text = await response.text();
      return res.send(text);
    }
  } catch (err: any) {
    console.error(`Error proxying ${req.method} ${req.originalUrl} to FastAPI:`, err.message);
    return res.status(502).json({
      error: 'Backend connection failed. Ensure FastAPI is running on port 8000 (uvicorn backend.main:app --port 8000).',
    });
  }
});

// Serve frontend assets
async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        watch: {
          ignored: [
            '**/backend/**',
            '**/tests/**',
            '**/*.py',
            '**/__pycache__/**',
            '**/.pytest_cache/**',
            '**/.env*',
            '**/scratch/**',
            '**/*.sql',
          ],
        },
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Digital Study Carrel dev server running at http://0.0.0.0:${PORT}`);
    console.log(`Routing /api requests to FastAPI backend at ${FASTAPI_TARGET}`);
  });
}

startServer();
