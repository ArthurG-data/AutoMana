// Augment @tanstack/router-core types with missing global types
declare global {
  // DOM API types that may be missing
  interface ScrollIntoViewOptions {
    behavior?: ScrollBehavior
    block?: ScrollLogicalPosition
    inline?: ScrollLogicalPosition
  }

  type ScrollBehavior = 'auto' | 'smooth'
  type ScrollLogicalPosition = 'start' | 'center' | 'end' | 'nearest'

  interface ScrollToOptions {
    left?: number
    top?: number
    behavior?: ScrollBehavior
  }

  type HeadersInit = Record<string, string>

  interface Worker {
    postMessage(message: any, transfer?: Transferable[]): void
    terminate(): void
    onmessage: ((this: Worker, ev: MessageEvent<any>) => any) | null
    onerror: ((this: Worker, ev: ErrorEvent) => any) | null
  }
}

// Add missing target property to HTMLAnchorElement
declare global {
  interface HTMLAnchorElement {
    target?: string
  }
}

export {}
