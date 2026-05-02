// Missing DOM API type definitions for @tanstack/router-core compatibility
declare global {
  interface ScrollIntoViewOptions {
    behavior?: 'auto' | 'smooth'
    block?: 'start' | 'center' | 'end' | 'nearest'
    inline?: 'start' | 'center' | 'end' | 'nearest'
  }

  type ScrollBehavior = 'auto' | 'smooth'

  interface ScrollToOptions {
    left?: number
    top?: number
    behavior?: 'auto' | 'smooth'
  }

  type HeadersInit = Record<string, string>

  interface Worker {
    postMessage(message: any, transfer?: Transferable[]): void
    terminate(): void
    onmessage: ((this: Worker, ev: MessageEvent<any>) => any) | null
    onerror: ((this: Worker, ev: ErrorEvent) => any) | null
  }

  namespace JSX {
    interface IntrinsicElements {
      // Ensure HTMLAnchorElement includes target attribute
    }
  }
}

// Extend HTMLAnchorElement if not already present
declare global {
  interface HTMLAnchorElement {
    target?: string
  }
}

export {}
