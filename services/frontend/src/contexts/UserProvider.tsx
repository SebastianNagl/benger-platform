'use client'

import { User } from '@/lib/api'
import React, { createContext, useCallback, useContext, useState } from 'react'

interface UserContextType {
  user: User | null
  setUser: (user: User | null) => void
  updateUser: (userData: Partial<User>) => void
}

const UserContext = createContext<UserContextType | null>(null)

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<User | null>(null)

  const setUser = useCallback((user: User | null) => {
    setUserState(user)
  }, [])

  const updateUser = useCallback((userData: Partial<User>) => {
    setUserState((prevUser) => (prevUser ? { ...prevUser, ...userData } : null))
  }, [])

  return (
    <UserContext.Provider value={{ user, setUser, updateUser }}>
      {children}
    </UserContext.Provider>
  )
}

export function useUser() {
  const context = useContext(UserContext)
  if (!context) {
    throw new Error('useUser must be used within a UserProvider')
  }
  return context
}
