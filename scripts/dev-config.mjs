// Both development servers must agree on the API port. Keep it separate from
// the conventional 8000 port often occupied by other local FastAPI projects.
export function backendPort(env = process.env) {
  const value = env.PUCHOO_API_PORT ?? "8001";
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535) {
    throw new Error("PUCHOO_API_PORT must be an integer between 1 and 65535.");
  }
  return Number(value);
}

export function backendTarget(env = process.env) {
  return `http://127.0.0.1:${backendPort(env)}`;
}
