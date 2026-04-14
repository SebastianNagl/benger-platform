import { Locator, Page } from '@playwright/test'

export class TasksListPage {
  readonly page: Page
  readonly taskRows: Locator
  readonly createTaskButton: Locator
  readonly searchInput: Locator
  readonly filterDropdown: Locator

  constructor(page: Page) {
    this.page = page
    this.taskRows = page.locator('[data-testid="task-row"]')
    this.createTaskButton = page.locator('button:has-text("Create Task")')
    this.searchInput = page.locator('[data-testid="task-search-input"]')
    this.filterDropdown = page.locator('[data-testid="task-filter-dropdown"]')
  }

  async goto() {
    await this.page.goto('/tasks')
  }

  async getTaskByName(taskName: string): Promise<Locator> {
    return this.page.locator(`[data-testid="task-row"]:has-text("${taskName}")`)
  }

  async clickTask(taskName: string) {
    const taskRow = await this.getTaskByName(taskName)
    await taskRow.click()
  }

  async searchForTask(searchTerm: string) {
    await this.searchInput.fill(searchTerm)
    await this.page.waitForTimeout(500) // Wait for search debounce
  }

  async getTaskCount(): Promise<number> {
    await this.taskRows.first().waitFor({ state: 'visible', timeout: 5000 })
    return await this.taskRows.count()
  }

  async waitForTasksToLoad() {
    await this.page.waitForSelector('[data-testid="task-row"]', {
      timeout: 10000,
    })
  }
}
