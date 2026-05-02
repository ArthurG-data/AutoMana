// src/vitest.d.ts
import type { Assertion, AsymmetricMatchersContaining } from 'vitest'

declare global {
  function beforeAll(fn: () => void | Promise<void>, timeout?: number): void
  function beforeEach(fn: () => void | Promise<void>, timeout?: number): void
  function afterEach(fn: () => void | Promise<void>, timeout?: number): void
  function afterAll(fn: () => void | Promise<void>, timeout?: number): void
  function describe(name: string, fn: () => void): void
  function it(name: string, fn: () => void | Promise<void>, timeout?: number): void
  function test(name: string, fn: () => void | Promise<void>, timeout?: number): void
}

export {}
