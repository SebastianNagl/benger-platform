// Create a single router instance that will be shared across all calls
export const mockRouterInstance = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}

export const useRouter = jest.fn(() => mockRouterInstance)

export const usePathname = jest.fn(() => '/')
export const useSearchParams = jest.fn(() => new URLSearchParams())
