export class MockWebSocket {
  static instances: MockWebSocket[] = []

  url: string
  readyState: number
  sentMessages: string[] = []

  onopen?: (event: Event) => void
  onclose?: (event: CloseEvent) => void
  onerror?: (event: Event) => void
  onmessage?: (event: MessageEvent) => void

  constructor(url: string, protocols?: string | string[]) {
    MockWebSocket.instances.push(this)
    this.url = url
    this.readyState = WebSocket.CONNECTING

    // Simulate connection opening
    setTimeout(() => {
      this.readyState = WebSocket.OPEN
      this.onopen?.({} as Event)
    }, 0)
  }

  send(data: string | ArrayBufferLike | Blob | ArrayBufferView) {
    if (this.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not open')
    }
    this.sentMessages.push(data.toString())
  }

  close(code?: number, reason?: string) {
    this.readyState = WebSocket.CLOSING
    setTimeout(() => {
      this.readyState = WebSocket.CLOSED
      this.onclose?.({
        code: code || 1000,
        reason: reason || '',
        wasClean: true,
      } as CloseEvent)
    }, 0)
  }

  // Test helper methods
  simulateMessage(data: any) {
    if (this.readyState === WebSocket.OPEN) {
      this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
    }
  }

  simulateError(error: Error) {
    this.readyState = WebSocket.CLOSED
    this.onerror?.({ ...error, target: this } as any)
  }

  simulateClose(code = 1000, reason = '') {
    this.close(code, reason)
  }

  static clear() {
    MockWebSocket.instances = []
  }

  static getByUrl(url: string): MockWebSocket | undefined {
    return MockWebSocket.instances.find((ws) => ws.url === url)
  }
}

// WebSocket event types for testing
export const WS_EVENTS = {
  ANNOTATION_UPDATE: 'annotation_update',
  USER_JOINED: 'user_joined',
  USER_LEFT: 'user_left',
  CURSOR_MOVE: 'cursor_move',
  SELECTION_CHANGE: 'selection_change',
  CONFLICT_DETECTED: 'conflict_detected',
  SYNC_REQUEST: 'sync_request',
  SYNC_RESPONSE: 'sync_response',
} as const

// Helper to create WebSocket messages
export const createWSMessage = (type: string, data: any) => ({
  type,
  data,
  timestamp: new Date().toISOString(),
})

// Helper to simulate collaboration scenarios
export const simulateCollaboration = {
  userJoins: (ws: MockWebSocket, userId: string, userName: string) => {
    ws.simulateMessage(
      createWSMessage(WS_EVENTS.USER_JOINED, {
        user: { id: userId, name: userName },
      })
    )
  },

  userLeaves: (ws: MockWebSocket, userId: string) => {
    ws.simulateMessage(
      createWSMessage(WS_EVENTS.USER_LEFT, {
        userId,
      })
    )
  },

  cursorMove: (
    ws: MockWebSocket,
    userId: string,
    position: { x: number; y: number }
  ) => {
    ws.simulateMessage(
      createWSMessage(WS_EVENTS.CURSOR_MOVE, {
        userId,
        position,
      })
    )
  },

  annotationUpdate: (ws: MockWebSocket, annotation: any) => {
    ws.simulateMessage(
      createWSMessage(WS_EVENTS.ANNOTATION_UPDATE, {
        annotation,
      })
    )
  },

  conflictDetected: (ws: MockWebSocket, localData: any, remoteData: any) => {
    ws.simulateMessage(
      createWSMessage(WS_EVENTS.CONFLICT_DETECTED, {
        local: localData,
        remote: remoteData,
      })
    )
  },
}
