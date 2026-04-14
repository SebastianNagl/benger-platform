/**
 * ProjectList component - Label Studio aligned project management
 *
 * This component replaces the old TaskList and follows Label Studio's
 * project-centric architecture while maintaining BenGER's design.
 */

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { Input } from '@/components/shared/Input'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/shared/Tabs'
import { useProjectStore } from '@/stores/projectStore'
import { useI18n } from '@/contexts/I18nContext'
import {
  ArchiveBoxIcon,
  ChartBarIcon,
  DocumentTextIcon,
  FolderIcon,
  PlusIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { formatDistanceToNow } from 'date-fns'
import { de } from 'date-fns/locale'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

export function ProjectList() {
  const { t } = useI18n()
  const router = useRouter()
  const { projects, loading, fetchProjects, setSearchQuery, searchQuery } =
    useProjectStore()

  const [activeTab, setActiveTab] = useState<'active' | 'archived'>('active')

  useEffect(() => {
    fetchProjects(1, 100)
  }, [fetchProjects])

  const filteredProjects = projects.filter((project) => {
    const matchesSearch =
      !searchQuery ||
      project.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      project.description?.toLowerCase().includes(searchQuery.toLowerCase())

    return matchesSearch
  })

  const handleCreateProject = () => {
    router.push('/projects/create')
  }

  const getProjectStats = (project: any) => {
    // Use server-calculated progress_percentage if available (Issue #257)
    const completionRate =
      project.progress_percentage !== undefined
        ? Math.round(project.progress_percentage)
        : project.task_count > 0
          ? Math.min(
              100,
              Math.round((project.annotation_count / project.task_count) * 100)
            )
          : 0

    return { completionRate }
  }

  if (loading && projects.length === 0) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">{t('projects.list.title')}</h1>
            <p className="text-muted-foreground mt-1">
              {t('projects.list.subtitle')}
            </p>
          </div>
          <Button onClick={handleCreateProject}>
            <PlusIcon className="mr-2 h-5 w-5" />
            {t('projects.list.newProject')}
          </Button>
        </div>

        {/* Search and Filters */}
        <div className="flex gap-4">
          <Input
            placeholder={t('projects.list.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-md"
          />
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="active">
        <TabsList className="mb-6">
          <TabsTrigger value="active">
            <FolderIcon className="mr-2 h-4 w-4" />
            {t('projects.list.activeProjects')}
          </TabsTrigger>
          <TabsTrigger value="archived">
            <ArchiveBoxIcon className="mr-2 h-4 w-4" />
            {t('projects.list.archived')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="active" className="mt-0">
          {filteredProjects.filter((p) => !p.is_archived).length === 0 ? (
            <Card className="p-12 text-center">
              <div>
                <FolderIcon className="text-muted-foreground mx-auto mb-4 h-12 w-12" />
                <h3 className="mb-2 text-lg font-medium">
                  {searchQuery
                    ? t('projects.list.noProjectsFound')
                    : activeTab === 'active'
                      ? t('projects.list.noActiveProjects')
                      : t('projects.list.noArchivedProjects')}
                </h3>
                <p className="text-muted-foreground mb-4">
                  {searchQuery
                    ? t('projects.list.tryAdjusting')
                    : t('projects.list.createFirst')}
                </p>
                {!searchQuery && activeTab === 'active' && (
                  <Button onClick={handleCreateProject}>
                    <PlusIcon className="mr-2 h-4 w-4" />
                    {t('projects.list.createProject')}
                  </Button>
                )}
              </div>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
              {filteredProjects
                .filter((p) => !p.is_archived)
                .map((project) => {
                  const { completionRate } = getProjectStats(project)

                  return (
                    <Card
                      key={project.id}
                      className="cursor-pointer transition-shadow hover:shadow-lg"
                      onClick={() => router.push(`/projects/${project.id}`)}
                    >
                      <div>
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h3 className="line-clamp-1">{project.title}</h3>
                            <p className="mt-1 line-clamp-2">
                              {project.description || t('projects.list.noDescription')}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div>
                        {/* Statistics */}
                        <div className="mb-4 grid grid-cols-2 gap-4">
                          <div>
                            <div className="text-muted-foreground flex items-center text-sm">
                              <DocumentTextIcon className="mr-1 h-4 w-4" />
                              {t('projects.list.tasks')}
                            </div>
                            <p className="text-2xl font-semibold">
                              {project.task_count}
                            </p>
                          </div>
                          <div>
                            <div className="text-muted-foreground flex items-center text-sm">
                              <ChartBarIcon className="mr-1 h-4 w-4" />
                              {t('projects.list.progress')}
                            </div>
                            <p className="text-2xl font-semibold">
                              {completionRate}%
                            </p>
                          </div>
                        </div>

                        {/* Progress Bar */}
                        <div className="bg-secondary mb-4 h-2 w-full rounded-full">
                          <div
                            className="bg-primary h-2 rounded-full transition-all"
                            style={{
                              width: `${Math.min(100, completionRate)}%`,
                            }}
                          />
                        </div>

                        {/* LLM Models */}
                        {project.llm_model_ids &&
                          project.llm_model_ids.length > 0 && (
                            <div className="mb-3 flex items-center gap-2">
                              <SparklesIcon className="text-muted-foreground h-4 w-4" />
                              <div className="flex flex-wrap gap-1">
                                {project.llm_model_ids.map(
                                  (modelId: string) => (
                                    <Badge
                                      key={modelId}
                                      variant="secondary"
                                      className="text-xs"
                                    >
                                      {modelId}
                                    </Badge>
                                  )
                                )}
                              </div>
                            </div>
                          )}

                        {/* Footer */}
                        <div className="text-muted-foreground flex items-center justify-between text-sm">
                          <span>{t('projects.list.annotations', { count: project.annotation_count })}</span>
                          <span>
                            {formatDistanceToNow(new Date(project.created_at), {
                              addSuffix: true,
                              locale: de,
                            })}
                          </span>
                        </div>
                      </div>
                    </Card>
                  )
                })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="archived" className="mt-0">
          {filteredProjects.filter((p) => p.is_archived).length === 0 ? (
            <Card className="p-12 text-center">
              <div>
                <ArchiveBoxIcon className="text-muted-foreground mx-auto mb-4 h-12 w-12" />
                <h3 className="mb-2 text-lg font-medium">
                  {t('projects.list.noArchivedProjects')}
                </h3>
                <p className="text-muted-foreground">
                  {t('projects.list.archivedAppear')}
                </p>
              </div>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredProjects
                .filter((p) => p.is_archived)
                .map((project) => (
                  <Link key={project.id} href={`/projects/${project.id}`}>
                    <Card className="h-full cursor-pointer transition-shadow hover:shadow-lg">
                      <div className="p-6">
                        <h3 className="mb-2 text-lg font-semibold">
                          {project.title}
                        </h3>
                        <p className="text-muted-foreground mb-4 line-clamp-2 text-sm">
                          {project.description || t('projects.list.noDescription')}
                        </p>
                        <Badge variant="secondary" className="mb-3">
                          {t('projects.list.archived')}
                        </Badge>
                      </div>
                    </Card>
                  </Link>
                ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
