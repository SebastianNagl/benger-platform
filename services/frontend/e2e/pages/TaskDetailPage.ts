import { Locator, Page } from '@playwright/test'

export class TaskDetailPage {
  readonly page: Page
  readonly taskTitle: Locator
  readonly annotateButton: Locator
  readonly deleteButton: Locator
  readonly editButton: Locator
  readonly statusBadge: Locator
  readonly questionsTab: Locator
  readonly annotationsTab: Locator
  readonly settingsTab: Locator

  constructor(page: Page) {
    this.page = page
    this.taskTitle = page.locator('[data-testid="task-title"]')
    this.annotateButton = page.locator('button:has-text("Annotate")')
    this.deleteButton = page.locator('button:has-text("Delete")')
    this.editButton = page.locator('button:has-text("Edit")')
    this.statusBadge = page.locator('[data-testid="task-status-badge"]')
    this.questionsTab = page.locator('[data-testid="task-questions-tab"]')
    this.annotationsTab = page.locator('[data-testid="task-annotations-tab"]')
    this.settingsTab = page.locator('[data-testid="task-settings-tab"]')
  }

  async goto(taskId: string) {
    await this.page.goto(`/tasks/${taskId}`)
  }

  async waitForTaskToLoad() {
    await this.taskTitle.waitFor({ state: 'visible', timeout: 10000 })
  }

  async getTaskTitle(): Promise<string> {
    return (await this.taskTitle.textContent()) || ''
  }

  async clickAnnotate() {
    await this.annotateButton.click()
  }

  async clickQuestionsTab() {
    await this.questionsTab.click()
  }

  async clickAnnotationsTab() {
    await this.annotationsTab.click()
  }

  async clickSettingsTab() {
    await this.settingsTab.click()
  }

  async deleteTask() {
    await this.deleteButton.click()
    // Handle confirmation dialog if it appears
    await this.page.locator('button:has-text("Confirm")').click()
  }
}
