/**
 * Vercel Serverless Function — keeps Render backend awake.
 * Called by Vercel Cron every 14 minutes.
 */
export default async function handler(req, res) {
  const RENDER_URL = process.env.VITE_API_BASE
    ? process.env.VITE_API_BASE.replace('/api', '/health')
    : 'https://hk-racing-quant-api.onrender.com/health';

  try {
    const response = await fetch(RENDER_URL, { method: 'GET' });
    const data = await response.json();
    return res.status(200).json({
      status: 'pinged',
      render_status: data,
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    return res.status(200).json({
      status: 'ping_failed',
      error: err.message,
      timestamp: new Date().toISOString(),
    });
  }
}
