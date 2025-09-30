// server.ts - Next.js Standalone + Socket.IO (friendly startup messages)
import { setupSocket } from '@/lib/socket';
import { createServer } from 'http';
import { Server } from 'socket.io';
import next from 'next';
import os from 'os';

const dev = process.env.NODE_ENV !== 'production';
const currentPort = Number(process.env.PORT || 3000);
// bindHost: you can set HOST env to '127.0.0.1' if you want localhost-only binding
const bindHost = process.env.HOST || '0.0.0.0';

// Helper to find a LAN IPv4 address (first non-internal IPv4)
function getLanIp(): string | null {
  const nets = os.networkInterfaces();
  for (const name of Object.keys(nets)) {
    const iface = nets[name];
    if (!iface) continue;
    for (const net of iface) {
      if (net.family === 'IPv4' && !net.internal) {
        return net.address;
      }
    }
  }
  return null;
}

// Custom server with Socket.IO integration
async function createCustomServer() {
  try {
    // Create Next.js app
    const nextApp = next({
      dev,
      dir: process.cwd(),
      conf: dev ? undefined : { distDir: './.next' }
    });

    await nextApp.prepare();
    const handle = nextApp.getRequestHandler();

    // Create HTTP server that will handle both Next.js and Socket.IO
    const server = createServer((req, res) => {
      // Skip socket.io requests from Next.js handler
      if (req.url?.startsWith('/api/socketio')) {
        return;
      }
      handle(req, res);
    });

    // Setup Socket.IO
    const io = new Server(server, {
      path: '/api/socketio',
      cors: {
        origin: "*",
        methods: ["GET", "POST"]
      }
    });

    setupSocket(io);

    // Start the server
    server.listen(currentPort, bindHost, () => {
      const lanIp = getLanIp();
      // Always show localhost (works even when bound to 0.0.0.0)
      console.log(`> Ready on http://localhost:${currentPort}`);
      // If bound to a specific host other than 0.0.0.0, show that too
      if (bindHost !== '0.0.0.0') {
        console.log(`> Server bound on http://${bindHost}:${currentPort}`);
      }
      // Show LAN address when available
      if (lanIp) {
        console.log(`> Accessible on your network at http://${lanIp}:${currentPort}`);
      }
      console.log(`> Socket.IO server running at ws://${bindHost}:${currentPort}/api/socketio`);
    });

  } catch (err) {
    console.error('Server startup error:', err);
    process.exit(1);
  }
}

// Start the server
createCustomServer();
