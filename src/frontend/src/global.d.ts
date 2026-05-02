// src/global.d.ts
// Global type declarations for missing DOM APIs

declare global {
  interface ScrollIntoViewOptions {
    behavior?: ScrollBehavior
    block?: ScrollLogicalPosition
    inline?: ScrollLogicalPosition
  }

  type ScrollBehavior = 'auto' | 'smooth'
  type ScrollLogicalPosition = 'start' | 'center' | 'end' | 'nearest'

  interface ScrollToOptions extends ScrollToPosition {
    behavior?: ScrollBehavior
  }

  interface ScrollToPosition {
    left?: number
    top?: number
  }

  type HeadersInit = Record<string, string>

  interface Worker {
    postMessage(message: any, transfer?: Transferable[]): void
    terminate(): void
    onmessage: ((this: Worker, ev: MessageEvent<any>) => any) | null
    onerror: ((this: Worker, ev: ErrorEvent) => any) | null
  }

  interface HTMLAnchorElement {
    target?: string
  }
}

export {}
