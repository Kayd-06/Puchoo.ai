import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(cleanup);

class EventSourceStub {
  addEventListener() {}
  close() {}
}

globalThis.EventSource = EventSourceStub;
