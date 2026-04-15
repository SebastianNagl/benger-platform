'use client'

import React, { createContext, useContext, useState } from 'react'

interface User {
  id: string
  username: string
  email: string
  name: string
  role: string
}

interface Organization {
  id: string
  name: string
  slug: string
}

interface AuthContextType {
  user: User | null
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isLoading: boolean
  organizations: Organization[]
  currentOrganization: Organization | null
  setCurrentOrganization: (org: Organization | null) => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function SimpleAuthProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [organizations, setOrganizations] = useState<Organization[]>([
    { id: '1', name: 'TUM', slug: 'tum' },
    { id: '2', name: 'Test Org', slug: 'test-org' },
  ])
  const [currentOrganization, setCurrentOrganization] =
    useState<Organization | null>(null)

  const login = async (username: string, password: string) => {
    setIsLoading(true)
    try {
      // Mock login - just set a fake user
      await new Promise((resolve) => setTimeout(resolve, 1000)) // Simulate API call
      const mockUser: User = {
        id: '1',
        username,
        email: `${username}@example.com`,
        name: username,
        role: 'user',
      }
      setUser(mockUser)
      setCurrentOrganization(organizations[0])
    } finally {
      setIsLoading(false)
    }
  }

  const logout = async () => {
    setIsLoading(true)
    try {
      await new Promise((resolve) => setTimeout(resolve, 500)) // Simulate API call
      setUser(null)
      setCurrentOrganization(null)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        login,
        logout,
        isLoading,
        organizations,
        currentOrganization,
        setCurrentOrganization,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
