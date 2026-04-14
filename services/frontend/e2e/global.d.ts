declare global {
  interface Window {
    mockUser?: {
      is_superadmin?: boolean
      role?: string
      [key: string]: any
    }
    __mockSelectedTasks?: any[]
    [key: string]: any
  }
}

export {}
