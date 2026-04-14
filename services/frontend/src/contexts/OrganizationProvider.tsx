'use client'

import { Organization } from '@/lib/api'
import { OrganizationManager } from '@/lib/auth/organizationManager'
import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react'

interface OrganizationContextType {
  organizations: Organization[]
  currentOrganization: Organization | null
  setOrganizations: (orgs: Organization[]) => void
  setCurrentOrganization: (org: Organization | null) => void
  manager: OrganizationManager
}

const OrganizationContext = createContext<OrganizationContextType | null>(null)

export function OrganizationProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [organizations, setOrganizationsState] = useState<Organization[]>([])
  const [currentOrganization, setCurrentOrganizationState] =
    useState<Organization | null>(null)

  // Create stable manager instance
  const manager = useMemo(() => new OrganizationManager(), [])

  const setOrganizations = useCallback(
    (orgs: Organization[]) => {
      setOrganizationsState(orgs)
      manager.setOrganizations(orgs)

      // Auto-select first organization if none selected
      if (!currentOrganization && orgs.length > 0) {
        setCurrentOrganizationState(orgs[0])
        manager.setCurrentOrganization(orgs[0])
      }
    },
    [manager, currentOrganization]
  )

  const setCurrentOrganization = useCallback(
    (org: Organization | null) => {
      setCurrentOrganizationState(org)
      manager.setCurrentOrganization(org)
    },
    [manager]
  )

  return (
    <OrganizationContext.Provider
      value={{
        organizations,
        currentOrganization,
        setOrganizations,
        setCurrentOrganization,
        manager,
      }}
    >
      {children}
    </OrganizationContext.Provider>
  )
}

export function useOrganization() {
  const context = useContext(OrganizationContext)
  if (!context) {
    throw new Error(
      'useOrganization must be used within an OrganizationProvider'
    )
  }
  return context
}
