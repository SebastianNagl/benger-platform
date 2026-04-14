/**
 * Project Members Management page
 *
 * Allows superadmins to assign projects to organizations and
 * organization admins/contributors to manage project members
 */

'use client'

import { UserAvatar } from '@/components/projects/UserAvatar'
import { Badge } from '@/components/shared/Badge'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/shared/Tabs'
import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useDeleteConfirm } from '@/hooks/useDialogs'
import { organizationsAPI } from '@/lib/api/organizations'
import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import {
  Dialog,
  DialogBackdrop,
  DialogPanel,
  DialogTitle,
} from '@headlessui/react'
import {
  ArrowLeftIcon,
  BuildingOfficeIcon,
  MagnifyingGlassIcon,
  TrashIcon,
  UserGroupIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { useParams, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

interface Organization {
  id: string
  name: string
  slug: string
  description?: string
}

interface ProjectMember {
  id: string
  user_id: string
  name: string
  email: string
  role: string
  is_direct_member: boolean
  organization_id: string | null
  organization_name: string | null
  added_at: string
}

interface OrganizationAssignment {
  organization_id: string
  organization_name: string
  assigned_at: string
  assigned_by: string
}

export default function ProjectMembersPage() {
  const router = useRouter()
  const params = useParams()
  const projectId = params?.id as string
  const { user } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()
  const confirmDelete = useDeleteConfirm()
  const { currentProject, fetchProject, loading } = useProjectStore()

  // State
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [projectOrganizations, setProjectOrganizations] = useState<
    OrganizationAssignment[]
  >([])
  const [projectMembers, setProjectMembers] = useState<ProjectMember[]>([])
  const [loadingOrgs, setLoadingOrgs] = useState(true)
  const [loadingMembers, setLoadingMembers] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [showAddOrgDialog, setShowAddOrgDialog] = useState(false)
  const [showAddMemberDialog, setShowAddMemberDialog] = useState(false)
  const [selectedOrgId, setSelectedOrgId] = useState('')
  const [selectedUserId, setSelectedUserId] = useState('')
  const [orgMembers, setOrgMembers] = useState<any[]>([])
  const [loadingOrgMembers, setLoadingOrgMembers] = useState(false)

  // Load project if not already loaded
  useEffect(() => {
    if (!currentProject || currentProject.id !== projectId) {
      fetchProject(projectId)
    }
  }, [projectId, currentProject, fetchProject])

  // Load organizations
  useEffect(() => {
    const loadOrganizations = async () => {
      try {
        setLoadingOrgs(true)
        const orgs = await organizationsAPI.getOrganizations()
        setOrganizations(orgs)

        // Load project organizations from API
        if (currentProject) {
          const projectOrgs = await projectsAPI.getOrganizations(projectId)
          setProjectOrganizations(projectOrgs)
        }
      } catch (error) {
        console.error('Failed to load organizations:', error)
        addToast(t('members.orgAddFailed'), 'error')
      } finally {
        setLoadingOrgs(false)
      }
    }

    if (user?.is_superadmin) {
      loadOrganizations()
    }
  }, [user, currentProject, projectId, addToast, t])

  // Load project members
  useEffect(() => {
    const loadProjectMembers = async () => {
      try {
        setLoadingMembers(true)
        // Load project members from API
        const members = await projectsAPI.getMembers(projectId)
        setProjectMembers(members)
      } catch (error) {
        console.error('Failed to load project members:', error)
        addToast(t('members.addFailed'), 'error')
      } finally {
        setLoadingMembers(false)
      }
    }

    if (currentProject) {
      loadProjectMembers()
    }
  }, [currentProject, projectId, addToast, t])

  // Load organization members when selecting org for member addition
  const loadOrgMembers = async (orgId: string) => {
    try {
      setLoadingOrgMembers(true)
      const members = await organizationsAPI.getOrganizationMembers(orgId)
      setOrgMembers(members)
    } catch (error) {
      console.error('Failed to load organization members:', error)
      addToast(t('members.addFailed'), 'error')
    } finally {
      setLoadingOrgMembers(false)
    }
  }

  const canManageOrganizations = () => {
    return user?.is_superadmin === true
  }

  const canManageMembers = () => {
    if (!user || !currentProject) return false

    // Superadmins can always manage members
    if (user.is_superadmin) return true

    // Check if user is admin or contributor in any of the project's organizations
    // For now, check only the primary organization
    const userOrgs = (user as any).organization_memberships || []
    return userOrgs.some(
      (membership: any) =>
        membership.organization_id === currentProject.organization_id &&
        (membership.role === 'ORG_ADMIN' || membership.role === 'CONTRIBUTOR')
    )
  }

  const handleAddOrganization = async () => {
    if (!selectedOrgId || !projectId) return

    try {
      const result = await projectsAPI.addOrganization(projectId, selectedOrgId)

      // Reload project organizations
      const projectOrgs = await projectsAPI.getOrganizations(projectId)
      setProjectOrganizations(projectOrgs)

      addToast(t('members.orgAdded'), 'success')
      setShowAddOrgDialog(false)
      setSelectedOrgId('')
    } catch (error) {
      console.error('Failed to add organization:', error)
      addToast(t('members.orgAddFailed'), 'error')
    }
  }

  const handleRemoveOrganization = async (orgId: string) => {
    if (
      !confirm(
        'Are you sure you want to remove this organization from the project?'
      )
    ) {
      return
    }

    try {
      await projectsAPI.removeOrganization(projectId, orgId)

      // Reload project organizations
      const projectOrgs = await projectsAPI.getOrganizations(projectId)
      setProjectOrganizations(projectOrgs)

      addToast(t('members.removed'), 'success')
    } catch (error) {
      console.error('Failed to remove organization:', error)
      addToast(t('members.removeFailed'), 'error')
    }
  }

  const handleAddMember = async () => {
    if (!selectedUserId || !projectId) return

    try {
      const member = orgMembers.find((m) => m.user_id === selectedUserId)
      if (!member) return

      const result = await projectsAPI.addMember(
        projectId,
        selectedUserId,
        member.role
      )

      // Reload project members
      const members = await projectsAPI.getMembers(projectId)
      setProjectMembers(members)

      addToast(t('members.added'), 'success')
      setShowAddMemberDialog(false)
      setSelectedUserId('')
    } catch (error) {
      console.error('Failed to add member:', error)
      addToast(t('members.addFailed'), 'error')
    }
  }

  const handleRemoveMember = async (userId: string) => {
    const member = projectMembers.find((m) => m.user_id === userId)
    const memberName = member ? member.name : 'this member'

    const confirmed = await confirmDelete(memberName)
    if (!confirmed) {
      return
    }

    try {
      await projectsAPI.removeMember(projectId, userId)

      // Reload project members
      const members = await projectsAPI.getMembers(projectId)
      setProjectMembers(members)

      addToast(t('members.removed'), 'success')
    } catch (error) {
      console.error('Failed to remove member:', error)
      addToast(t('members.removeFailed'), 'error')
    }
  }

  const filteredMembers = projectMembers.filter((member) => {
    if (!searchQuery) return true
    const query = searchQuery.toLowerCase()
    return (
      member.name.toLowerCase().includes(query) ||
      member.email.toLowerCase().includes(query) ||
      (member.organization_name &&
        member.organization_name.toLowerCase().includes(query))
    )
  })

  if (!currentProject) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            Loading project...
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <Breadcrumb
          items={[
            {
              label: t('navigation.dashboard') || 'Dashboard',
              href: '/dashboard',
            },
            {
              label: t('navigation.projects') || 'Projects',
              href: '/projects',
            },
            { label: currentProject.title, href: `/projects/${projectId}` },
            {
              label: t('navigation.members') || 'Members',
              href: `/projects/${projectId}/members`,
            },
          ]}
        />

        <div className="mt-4 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
              {t('members.title')}
            </h1>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              {t('members.description')}
            </p>
          </div>

          <Button
            onClick={() => router.push(`/projects/${projectId}`)}
            variant="outline"
          >
            <ArrowLeftIcon className="mr-2 h-4 w-4" />
            {t('members.backToProject')}
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="members" className="space-y-6">
        <TabsList>
          <TabsTrigger value="members">
            {t('projects.tabs.members')}
          </TabsTrigger>
          {canManageOrganizations() && (
            <TabsTrigger value="organizations">
              {t('members.organizations')}
            </TabsTrigger>
          )}
        </TabsList>

        {/* Members Tab */}
        <TabsContent value="members">
          <Card>
            <div className="p-6">
              <div className="mb-6 flex items-center justify-between">
                <div className="max-w-sm flex-1">
                  <div className="relative">
                    <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 transform text-zinc-400" />
                    <Input
                      placeholder={t('members.searchPlaceholder')}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>

                {canManageMembers() && (
                  <Button
                    onClick={() => setShowAddMemberDialog(true)}
                    variant="primary"
                  >
                    <UserPlusIcon className="mr-2 h-4 w-4" />
                    {t('members.addMember')}
                  </Button>
                )}
              </div>

              {loadingMembers ? (
                <div className="py-12 text-center">
                  <div className="mx-auto h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
                </div>
              ) : filteredMembers.length === 0 ? (
                <div className="py-12 text-center">
                  <UserGroupIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400" />
                  <p className="text-zinc-600 dark:text-zinc-400">
                    {searchQuery
                      ? t('members.noMembersSearch')
                      : t('members.noMembers')}
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {filteredMembers.map((member) => (
                    <div
                      key={member.id}
                      className="flex items-center justify-between rounded-lg border border-zinc-200 p-4 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800/50"
                    >
                      <div className="flex items-center space-x-4">
                        <UserAvatar name={member.name} size="md" />
                        <div>
                          <p className="font-medium text-zinc-900 dark:text-white">
                            {member.name}
                          </p>
                          <p className="text-sm text-zinc-600 dark:text-zinc-400">
                            {member.email}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center space-x-4">
                        <div className="text-right">
                          <Badge className="mb-1">
                            {member.role.replace('_', ' ')}
                          </Badge>
                          <p className="text-xs text-zinc-500 dark:text-zinc-400">
                            {member.organization_name ||
                              t('members.noOrganization')}
                          </p>
                        </div>

                        {canManageMembers() && member.is_direct_member && (
                          <Button
                            onClick={() => handleRemoveMember(member.user_id)}
                            variant="outline"
                            className="text-red-600 hover:text-red-700 dark:text-red-400"
                          >
                            <TrashIcon className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </TabsContent>

        {/* Organizations Tab (Superadmin only) */}
        {canManageOrganizations() && (
          <TabsContent value="organizations">
            <Card>
              <div className="p-6">
                <div className="mb-6 flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                      {t('members.organizationAccess')}
                    </h3>
                    <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('members.organizationAccessDescription')}
                    </p>
                  </div>

                  <Button
                    onClick={() => setShowAddOrgDialog(true)}
                    variant="primary"
                  >
                    <BuildingOfficeIcon className="mr-2 h-4 w-4" />
                    {t('members.addOrganization')}
                  </Button>
                </div>

                {loadingOrgs ? (
                  <div className="py-12 text-center">
                    <div className="mx-auto h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
                  </div>
                ) : projectOrganizations.length === 0 ? (
                  <div className="py-12 text-center">
                    <BuildingOfficeIcon className="mx-auto mb-4 h-12 w-12 text-zinc-400" />
                    <p className="text-zinc-600 dark:text-zinc-400">
                      {t('members.noOrganizationsAssigned')}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {projectOrganizations.map((org) => (
                      <div
                        key={org.organization_id}
                        className="flex items-center justify-between rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
                      >
                        <div>
                          <p className="font-medium text-zinc-900 dark:text-white">
                            {org.organization_name}
                          </p>
                          <p className="text-sm text-zinc-600 dark:text-zinc-400">
                            Added{' '}
                            {formatDistanceToNow(new Date(org.assigned_at), {
                              addSuffix: true,
                            })}{' '}
                            by {org.assigned_by}
                          </p>
                        </div>

                        {projectOrganizations.length > 1 && (
                          <Button
                            onClick={() =>
                              handleRemoveOrganization(org.organization_id)
                            }
                            variant="outline"
                            className="text-red-600 hover:text-red-700 dark:text-red-400"
                          >
                            <TrashIcon className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      {/* Add Organization Dialog */}
      <Dialog
        open={showAddOrgDialog}
        onClose={() => {
          setShowAddOrgDialog(false)
          setSelectedOrgId('')
        }}
        className="relative z-50"
      >
        <DialogBackdrop className="fixed inset-0 bg-black/50" />

        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
            <DialogTitle className="mb-4 text-lg font-medium text-zinc-900 dark:text-white">
              {t('members.addOrganization')}
            </DialogTitle>

            <div className="space-y-4">
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                Select an organization to grant access to this project
              </p>

              <div>
                <label className="mb-2 block text-sm font-medium">
                  Organization
                </label>
                <Select
                  value={selectedOrgId}
                  onValueChange={setSelectedOrgId}
                  displayValue={
                    selectedOrgId
                      ? organizations.find((org) => org.id === selectedOrgId)?.name
                      : undefined
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t('members.selectOrganization')} />
                  </SelectTrigger>
                  <SelectContent>
                    {organizations
                      .filter(
                        (org) =>
                          !projectOrganizations.some(
                            (po) => po.organization_id === org.id
                          )
                      )
                      .map((org) => (
                        <SelectItem key={org.id} value={org.id}>
                          {org.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex justify-end space-x-3">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowAddOrgDialog(false)
                    setSelectedOrgId('')
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={handleAddOrganization}
                  disabled={!selectedOrgId}
                >
                  {t('members.addOrganization')}
                </Button>
              </div>
            </div>
          </DialogPanel>
        </div>
      </Dialog>

      {/* Add Member Dialog */}
      <Dialog
        open={showAddMemberDialog}
        onClose={() => {
          setShowAddMemberDialog(false)
          setSelectedUserId('')
          setSelectedOrgId('')
        }}
        className="relative z-50"
      >
        <DialogBackdrop className="fixed inset-0 bg-black/50" />

        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900">
            <DialogTitle className="mb-4 text-lg font-medium text-zinc-900 dark:text-white">
              {t('members.addProjectMember')}
            </DialogTitle>

            <div className="space-y-4">
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                Add members from your organizations to this project
              </p>

              <div>
                <label className="mb-2 block text-sm font-medium">
                  Organization
                </label>
                <Select
                  value={selectedOrgId}
                  onValueChange={(v) => {
                    setSelectedOrgId(v)
                    setSelectedUserId('')
                    if (v) {
                      loadOrgMembers(v)
                    }
                  }}
                  displayValue={
                    selectedOrgId
                      ? projectOrganizations.find((org) => org.organization_id === selectedOrgId)?.organization_name
                      : undefined
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder={t('members.selectOrganization')} />
                  </SelectTrigger>
                  <SelectContent>
                    {projectOrganizations.map((org) => (
                      <SelectItem
                        key={org.organization_id}
                        value={org.organization_id}
                      >
                        {org.organization_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {selectedOrgId && (
                <div>
                  <label className="mb-2 block text-sm font-medium">
                    Member
                  </label>
                  {loadingOrgMembers ? (
                    <div className="py-4 text-center">
                      <div className="mx-auto h-6 w-6 animate-spin rounded-full border-b-2 border-emerald-500"></div>
                    </div>
                  ) : (
                    <Select
                      value={selectedUserId}
                      onValueChange={setSelectedUserId}
                      displayValue={
                        selectedUserId
                          ? (() => {
                              const member = orgMembers.find((m) => m.user_id === selectedUserId)
                              return member ? `${member.user_name} (${member.user_email}) - ${member.role}` : ''
                            })()
                          : undefined
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder={t('members.selectMember')} />
                      </SelectTrigger>
                      <SelectContent>
                        {orgMembers
                          .filter(
                            (member) =>
                              !projectMembers.some(
                                (pm) => pm.user_id === member.user_id
                              )
                          )
                          .map((member) => (
                            <SelectItem key={member.user_id} value={member.user_id}>
                              {member.user_name} ({member.user_email}) -{' '}
                              {member.role}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              )}

              <div className="flex justify-end space-x-3">
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowAddMemberDialog(false)
                    setSelectedUserId('')
                    setSelectedOrgId('')
                  }}
                >
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleAddMember} disabled={!selectedUserId}>
                  {t('members.addMember')}
                </Button>
              </div>
            </div>
          </DialogPanel>
        </div>
      </Dialog>
    </div>
  )
}
