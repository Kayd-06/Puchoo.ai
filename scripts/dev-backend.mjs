import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';

const isWindows = process.platform === 'win32';
const virtualenvPython = isWindows
  ? (existsSync('.venv\\Scripts\\python.exe') ? '.venv\\Scripts\\python.exe' : 'venv\\Scripts\\python.exe')
  : (existsSync('.venv/bin/python') ? '.venv/bin/python' : 'python3');

const server = spawn(
  virtualenvPython,
  ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'],
  { stdio: 'inherit' },
);

server.on('exit', (code) => process.exit(code ?? 1));
