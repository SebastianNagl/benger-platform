/**
 * Project store - Label Studio aligned state management
 *
 * This store manages the project state following Label Studio patterns
 * while maintaining BenGER's LLM capabilities.
 */

import { projectsAPI } from '@/lib/api/projects'
import { logger } from '@/lib/utils/logger'
import { translate as t } from '@/lib/utils/translate'
import { Annotation, Project, Task } from '@/types/labelStudio'
import { toast } from '@/components/shared/Toast'
import { create } from 'zustand'
import { devtools } from 'zustand/middleware'

interface ProjectStore {
  // State
  projects: Project[]
  currentProject: Project | null
  currentTask: Task | null
  currentTaskPosition: number | null
  currentTaskTotal: number | null
  loading: boolean
  error: string | null
  searchQuery: string
  // Task cycling state
  taskCycle: Task[]
  currentTaskIndex: number
  // Annotation completion state
  allTasksCompleted: boolean
  // Pagination state
  currentPage: number
  pageSize: number
  totalProjects: number
  totalPages: number
  // Configuration tracking
  labelConfigVersion: number

  // Project actions
  fetchProjects: (
    page?: number,
    pageSize?: number,
    isArchived?: boolean
  ) => Promise<void>
  fetchProject: (projectId: string) => Promise<void>
  createProject: (data: {
    title: string
    description?: string
    label_config?: string
  }) => Promise<Project>
  updateProject: (projectId: string, updates: Partial<Project>) => Promise<void>
  selectProject: (projectId: string) => void
  archiveProject: (projectId: string) => Promise<void>
  deleteProject: (projectId: string) => Promise<void>

  // Task actions
  fetchProjectTasks: (projectId: string, excludeMyAnnotations?: boolean) => Promise<Task[]>
  getNextTask: (projectId: string) => Promise<Task | null>
  setTaskByIndex: (index: number) => void
  advanceToNextTask: () => void
  completeCurrentTask: () => void | Promise<void>
  importData: (
    projectId: string,
    data: any[],
    extras?: {
      evaluation_runs?: any[]
      human_evaluation_configs?: any[]
      human_evaluation_sessions?: any[]
      human_evaluation_results?: any[]
      preference_rankings?: any[]
      likert_scale_evaluations?: any[]
      korrektur_comments?: any[]
    }
  ) => Promise<void>

  // Annotation actions
  createAnnotation: (taskId: string, result: any[]) => Promise<Annotation>
  skipTask: (comment?: string) => Promise<void>
  createAnnotationInternal: (
    taskId: string,
    data: any,
    skipAdvance?: boolean
  ) => Promise<Annotation>

  evaluateLLMResponses: (projectId: string) => Promise<void>

  // UI actions
  setSearchQuery: (query: string) => void
  setCurrentPage: (page: number) => void
  setPageSize: (size: number) => void
  clearError: () => void
  resetAnnotationCompletion: () => void
}

export const useProjectStore = create<ProjectStore>()(
  devtools(
    (set, get) => ({
      // Initial state
      projects: [],
      currentProject: null,
      currentTask: null,
      currentTaskPosition: null,
      currentTaskTotal: null,
      loading: false,
      error: null,
      searchQuery: '',
      // Task cycling
      taskCycle: [],
      currentTaskIndex: 0,
      // Annotation completion
      allTasksCompleted: false,
      currentPage: 1,
      pageSize: 30, // Reduced from 100 to improve load performance
      totalProjects: 0,
      totalPages: 0,
      labelConfigVersion: 0,

      // Project actions
      fetchProjects: async (
        page?: number,
        pageSize?: number,
        isArchived?: boolean
      ) => {
        const currentPageToUse = page ?? get().currentPage
        const pageSizeToUse = pageSize ?? get().pageSize
        const search = get().searchQuery

        set({ loading: true, error: null })
        try {
          const response = await projectsAPI.list(
            currentPageToUse,
            pageSizeToUse,
            search,
            isArchived
          )

          // Ensure response has the expected structure
          const projects = response?.items || []
          const total = response?.total || 0
          const pages = response?.pages || 1

          set({
            projects: Array.isArray(projects) ? projects : [],
            loading: false,
            currentPage: currentPageToUse,
            pageSize: pageSizeToUse,
            totalProjects: total,
            totalPages: pages,
          })
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.fetchFailed')
          set({ error: message, loading: false, projects: [] })
          toast(message, 'error')
        }
      },

      fetchProject: async (projectId: string) => {
        set({ loading: true, error: null })
        try {
          const project = await projectsAPI.get(projectId)
          set((state) => {
            // Check if project exists in the list, if not add it
            const existingIndex = state.projects.findIndex(
              (p) => p.id === projectId
            )
            let updatedProjects = state.projects

            if (existingIndex >= 0) {
              // Update existing project
              updatedProjects = state.projects.map((p) =>
                p.id === projectId ? project : p
              )
            } else {
              // Add new project to the list
              updatedProjects = [...state.projects, project]
            }

            return {
              projects: updatedProjects,
              currentProject: project,
              loading: false,
              // Clear task cycle when switching projects
              taskCycle: [],
              currentTaskIndex: 0,
            }
          })
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.fetchOneFailed')
          set({ error: message, loading: false })
          toast(message, 'error')
        }
      },

      createProject: async (data: {
        title: string
        description?: string
        label_config?: string
      }) => {
        set({ loading: true, error: null })
        try {
          const project = await projectsAPI.create(data)
          set((state) => ({
            projects: [...state.projects, project],
            currentProject: project,
            loading: false,
          }))
          toast(t('store.project.created'), 'success')
          return project
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.createFailed')
          set({ error: message, loading: false })
          toast(message, 'error')
          throw error
        }
      },

      updateProject: async (projectId: string, updates: Partial<Project>) => {
        set({ loading: true, error: null })
        try {
          const updatedProject = await projectsAPI.update(projectId, updates)
          set((state) => ({
            projects: state.projects.map((p) =>
              p.id === projectId ? updatedProject : p
            ),
            currentProject:
              state.currentProject?.id === projectId
                ? updatedProject
                : state.currentProject,
            loading: false,
            // Increment config version when label_config changes
            labelConfigVersion:
              'label_config' in updates
                ? state.labelConfigVersion + 1
                : state.labelConfigVersion,
          }))
          toast(t('store.project.updated'), 'success')
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.updateFailed')
          set({ error: message, loading: false })
          toast(message, 'error')
        }
      },

      selectProject: (projectId: string) => {
        const project = get().projects.find((p) => p.id === projectId)
        set({ currentProject: project || null })
      },

      archiveProject: async (projectId: string) => {
        await get().updateProject(projectId, { is_archived: true })
      },

      unarchiveProject: async (projectId: string) => {
        await get().updateProject(projectId, { is_archived: false })
      },

      deleteProject: async (projectId: string) => {
        set({ loading: true, error: null })
        try {
          await projectsAPI.delete(projectId)
          set((state) => ({
            projects: state.projects.filter((p) => p.id !== projectId),
            currentProject:
              state.currentProject?.id === projectId
                ? null
                : state.currentProject,
            loading: false,
          }))
          toast(t('store.project.deleted'), 'success')
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.deleteFailed')
          set({ error: message, loading: false })
          toast(message, 'error')
        }
      },

      // Task actions
      fetchProjectTasks: async (projectId: string, excludeMyAnnotations?: boolean) => {
        set({ loading: true, error: null })
        try {
          // Fetch all tasks by using pagination if necessary
          let allTasks: Task[] = []
          let page = 1
          const pageSize = 100 // Maximum API limit

          while (true) {
            const tasks = await projectsAPI.getTasks(projectId, {
              page,
              pageSize,
              excludeMyAnnotations,
            })
            allTasks.push(...tasks)

            // If we got less than pageSize tasks, we've reached the end
            if (tasks.length < pageSize) {
              break
            }
            page++
          }

          // Update taskCycle so setTaskByIndex works after this call
          set({
            loading: false,
            taskCycle: allTasks,
            currentTaskTotal: allTasks.length,
          })
          return allTasks
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.fetchTasksFailed')
          set({ error: message, loading: false })
          toast(message, 'error')
          return []
        }
      },

      getNextTask: async (projectId: string) => {
        set({ loading: true, error: null })
        try {
          const state = get()
          const project = state.currentProject
          // Auto mode: skip pre-loading, always use API /next (pull model)
          const isAutoMode = project?.assignment_mode === 'auto'

          // Pre-load task cycle for open/manual modes only
          if (!isAutoMode && state.taskCycle.length === 0) {
            // Use excludeMyAnnotations so the backend filters out tasks
            // the current user has already annotated (per-user, not global is_labeled)
            const tasks = await get().fetchProjectTasks(projectId, true)
            if (tasks && tasks.length > 0) {
              // Backend already excludes user's completed tasks and applies
              // randomized ordering when project.randomize_task_order is enabled
              set({
                taskCycle: tasks,
                currentTaskIndex: 0,
                currentTaskTotal: tasks.length,
              })
            }
            // If no tasks returned, fall through to API fallback below
            // which correctly distinguishes "no tasks in project" from
            // "user has completed all tasks"
          }

          const currentState = get()
          const { taskCycle, currentTaskIndex } = currentState

          // Use local cycle for open/manual modes only
          if (!isAutoMode && taskCycle.length > 0) {
            // Get current task or advance to next
            const currentTask = taskCycle[currentTaskIndex]

            set({
              currentTask: currentTask,
              currentTaskPosition: currentTaskIndex + 1,
              currentTaskTotal: taskCycle.length,
              loading: false,
            })

            return currentTask
          }

          // API-based approach (always used for auto mode, fallback for others)
          const result = await projectsAPI.getNextTask(projectId)
          if (result.task) {
            set({
              currentTask: result.task,
              currentTaskPosition: result.current_position || null,
              currentTaskTotal: result.total_tasks || null,
              loading: false,
            })
            return result.task
          } else {
            set({
              currentTask: null,
              currentTaskPosition: null,
              currentTaskTotal: null,
              loading: false,
            })
            toast(t('store.project.noMoreTasks'), 'info')
            return null
          }
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.nextTaskFailed')
          set({ error: message, loading: false })
          toast(message, 'error')
          return null
        }
      },

      setTaskByIndex: (index: number) => {
        const state = get()
        const { taskCycle } = state

        if (taskCycle.length > 0 && index >= 0 && index < taskCycle.length) {
          const task = taskCycle[index]

          set({
            currentTaskIndex: index,
            currentTask: task,
            currentTaskPosition: index + 1,
            currentTaskTotal: taskCycle.length,
          })

          logger.debug(`Set current task to index ${index} (${task?.id})`)
        } else {
          console.warn(
            `Invalid task index ${index} for task cycle of length ${taskCycle.length}`
          )
        }
      },

      advanceToNextTask: () => {
        const state = get()
        const { taskCycle, currentTaskIndex } = state

        if (taskCycle.length > 0) {
          let nextIndex = (currentTaskIndex + 1) % taskCycle.length

          // Check if we're looping back to the beginning
          if (nextIndex === 0 && currentTaskIndex > 0) {
            toast(t('store.project.allTasksCompletedRestart'), 'info')
          }

          // Get the next task and update all related state
          const nextTask = taskCycle[nextIndex] || null

          set({
            currentTaskIndex: nextIndex,
            currentTask: nextTask,
            currentTaskPosition: nextIndex + 1,
            currentTaskTotal: taskCycle.length,
          })
        }
      },

      // Remove the current task from the cycle and check for completion.
      // Used after questionnaire/evaluation modals close (where skipAdvance was true).
      completeCurrentTask: async () => {
        const isAutoMode = get().currentProject?.assignment_mode === 'auto'

        if (isAutoMode) {
          // Auto mode: fetch next task from API /next (pull model)
          const projectId = get().currentProject?.id
          if (projectId) {
            const nextTask = await get().getNextTask(projectId)
            if (!nextTask) {
              set({ allTasksCompleted: true })
            }
          }
          return
        }

        // Open/manual mode: manipulate local task cycle
        const state = get()
        const { taskCycle, currentTaskIndex } = state

        // Remove the completed task from the cycle
        const updatedCycle = taskCycle.filter((_, i) => i !== currentTaskIndex)

        if (updatedCycle.length === 0) {
          // All tasks done — trigger redirect via allTasksCompleted
          set({
            taskCycle: [],
            currentTask: null,
            currentTaskPosition: null,
            currentTaskTotal: null,
            allTasksCompleted: true,
          })
        } else {
          // Move to next task (stay at same index since we removed one)
          const nextIndex =
            currentTaskIndex >= updatedCycle.length ? 0 : currentTaskIndex
          const nextTask = updatedCycle[nextIndex]

          set({
            taskCycle: updatedCycle,
            currentTaskIndex: nextIndex,
            currentTask: nextTask,
            currentTaskPosition: nextIndex + 1,
            currentTaskTotal: updatedCycle.length,
          })
        }
      },

      importData: async (
        projectId: string,
        data: any[],
        extras?: Record<string, unknown>
      ) => {
        set({ loading: true, error: null })
        try {
          const result = await projectsAPI.importData(projectId, {
            data,
            ...(extras || {}),
          })
          set({ loading: false })
          toast(t('store.project.imported', { count: result.created }), 'success')

          // Update project task count
          // If this is the current project, fetch its updated data
          const currentProject = get().currentProject
          if (currentProject && currentProject.id === projectId) {
            await get().fetchProject(projectId)
          } else {
            // Otherwise just refresh the projects list
            await get().fetchProjects()
          }
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.importFailed')
          set({ error: message, loading: false })
          toast(message, 'error')
        }
      },

      // Annotation actions
      createAnnotationInternal: async (
        taskId: string,
        data: any,
        skipAdvance: boolean = false
      ) => {
        logger.debug('createAnnotationInternal called', { taskId, skipAdvance })
        try {
          const annotation = await projectsAPI.createAnnotation(taskId, data)
          logger.debug('Annotation created successfully:', annotation)

          if (!skipAdvance) {
            logger.debug('Auto-advancing to next task...')
            const isAutoMode = get().currentProject?.assignment_mode === 'auto'

            if (isAutoMode) {
              // Auto mode: fetch next task from API /next (pull model)
              const projectId = get().currentProject?.id
              if (projectId) {
                const nextTask = await get().getNextTask(projectId)
                if (!nextTask) {
                  set({ allTasksCompleted: true })
                }
              }
            } else {
              // Open/manual mode: manipulate local task cycle
              const state = get()
              const { taskCycle, currentTaskIndex } = state

              // Remove the annotated task from the cycle
              const updatedCycle = taskCycle.filter(
                (_, i) => i !== currentTaskIndex
              )

              if (updatedCycle.length === 0) {
                // All tasks annotated - trigger completion
                set({
                  taskCycle: [],
                  currentTask: null,
                  currentTaskPosition: null,
                  currentTaskTotal: null,
                  allTasksCompleted: true,
                })
              } else {
                // Move to next task (stay at same index since we removed one)
                const nextIndex =
                  currentTaskIndex >= updatedCycle.length ? 0 : currentTaskIndex
                const nextTask = updatedCycle[nextIndex]

                set({
                  taskCycle: updatedCycle,
                  currentTaskIndex: nextIndex,
                  currentTask: nextTask,
                  currentTaskPosition: nextIndex + 1,
                  currentTaskTotal: updatedCycle.length,
                })
              }
            }
          } else {
            logger.debug('Skipping auto-advance as requested')
          }

          return annotation
        } catch (error) {
          console.error('createAnnotationInternal error:', error)
          throw error
        }
      },

      createAnnotation: async (taskId: string, result: any[]) => {
        set({ loading: true, error: null })
        try {
          const annotation = await get().createAnnotationInternal(taskId, {
            result,
            lead_time: Math.random() * 60, // TODO: Track actual time
          })
          set({ loading: false })

          // Check if all tasks were completed
          if (get().allTasksCompleted) {
            toast(t('store.project.allTasksAnnotated'), 'success')
          } else {
            toast(t('store.project.annotationSaved'), 'success')
          }

          return annotation
        } catch (error) {
          const message =
            error instanceof Error ? error.message : t('store.project.annotationFailed')

          // Handle "Maximum annotations limit reached" gracefully
          // This means the task is fully annotated - advance to next task
          if (message.includes('Maximum annotations limit reached')) {
            const isAutoMode = get().currentProject?.assignment_mode === 'auto'

            if (isAutoMode) {
              // Auto mode: fetch next task from API
              const projectId = get().currentProject?.id
              set({ loading: false })
              if (projectId) {
                const nextTask = await get().getNextTask(projectId)
                if (!nextTask) {
                  set({ allTasksCompleted: true })
                  toast(t('store.project.allTasksAnnotated'), 'success')
                  return null as unknown as Annotation
                }
              }
            } else {
              const state = get()
              const { taskCycle, currentTaskIndex } = state

              // Remove the fully-annotated task from the cycle
              const updatedCycle = taskCycle.filter(
                (_, i) => i !== currentTaskIndex
              )

              if (updatedCycle.length === 0) {
                // All tasks are fully annotated - trigger auto-redirect
                set({
                  taskCycle: [],
                  currentTask: null,
                  currentTaskPosition: null,
                  currentTaskTotal: null,
                  loading: false,
                  allTasksCompleted: true,
                })
                toast(t('store.project.allTasksAnnotated'), 'success')
                return null as unknown as Annotation
              }

              // Advance to next available task
              const nextIndex =
                currentTaskIndex >= updatedCycle.length ? 0 : currentTaskIndex
              const nextTask = updatedCycle[nextIndex]

              set({
                taskCycle: updatedCycle,
                currentTaskIndex: nextIndex,
                currentTask: nextTask,
                currentTaskPosition: nextIndex + 1,
                currentTaskTotal: updatedCycle.length,
                loading: false,
              })
            }
            toast(t('store.project.taskFullyAnnotated'), 'info')
            return null as unknown as Annotation
          }

          set({ error: message, loading: false })
          toast(message, 'error')
          throw error
        }
      },

      skipTask: async (comment?: string) => {
        const currentTask = get().currentTask
        const currentProject = get().currentProject

        if (!currentTask || !currentProject) return

        try {
          // Call skip endpoint with optional comment
          const response = await fetch(
            `/api/projects/${currentProject.id}/tasks/${currentTask.id}/skip`,
            {
              method: 'POST',
              credentials: 'include',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ comment: comment || null }),
            }
          )

          if (!response.ok) {
            const errorData = await response.json()
            throw new Error(errorData.detail || t('store.project.skipFailed'))
          }

          // Handle task cycling after skip
          const isAutoMode = currentProject?.assignment_mode === 'auto'

          if (isAutoMode) {
            // Auto mode: fetch next task from API /next (pull model)
            if (currentProject.id) {
              const nextTask = await get().getNextTask(currentProject.id)
              if (!nextTask) {
                set({ allTasksCompleted: true })
              }
            }
          } else if (currentProject.skip_queue === 'requeue_for_me') {
            // Keep task in cycle, just advance to next
            get().advanceToNextTask()
          } else {
            // requeue_for_others or ignore_skipped: remove from this user's cycle
            const { taskCycle, currentTaskIndex } = get()
            const updatedCycle = taskCycle.filter((_, i) => i !== currentTaskIndex)

            if (updatedCycle.length === 0) {
              set({
                taskCycle: [],
                currentTask: null,
                currentTaskPosition: null,
                currentTaskTotal: null,
                allTasksCompleted: true,
              })
            } else {
              const nextIndex = currentTaskIndex >= updatedCycle.length ? 0 : currentTaskIndex
              set({
                taskCycle: updatedCycle,
                currentTaskIndex: nextIndex,
                currentTask: updatedCycle[nextIndex],
                currentTaskPosition: nextIndex + 1,
                currentTaskTotal: updatedCycle.length,
              })
            }
          }
          toast(t('store.project.taskSkipped'), 'info')
        } catch (error) {
          console.error('Skip task error:', error)
          const errorMessage =
            error instanceof Error ? error.message : t('store.project.skipFailed')
          toast(errorMessage, 'error')
          throw error
        }
      },

      evaluateLLMResponses: async (projectId: string) => {
        // TODO: Implement LLM evaluation
        toast(t('store.project.evaluationNotImplemented'), 'info')
      },

      // UI actions
      setSearchQuery: (query: string) => {
        set({ searchQuery: query, currentPage: 1 }) // Reset to page 1 on search
      },

      setCurrentPage: (page: number) => {
        set({ currentPage: page })
        get().fetchProjects(page)
      },

      setPageSize: (size: number) => {
        set({ pageSize: size, currentPage: 1 }) // Reset to page 1 on size change
        get().fetchProjects(1, size)
      },

      clearError: () => {
        set({ error: null })
      },

      resetAnnotationCompletion: () => {
        set({ allTasksCompleted: false })
      },
    }),
    {
      name: 'project-store',
    }
  )
)
