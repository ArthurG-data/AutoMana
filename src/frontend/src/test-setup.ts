// src/frontend/src/test-setup.ts
import '@testing-library/jest-dom'
import { server } from './mocks/server'

// IntersectionObserver is not implemented in jsdom — stub it so components that
// set up observers during render don't throw in the test environment.
global.IntersectionObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof IntersectionObserver

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
