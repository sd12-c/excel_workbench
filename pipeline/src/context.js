import { createContext, useContext } from 'react'

export const PipelineContext = createContext(null)

export function usePipelineActions() {
  const value = useContext(PipelineContext)
  if (!value) {
    return {
      openConfig: () => {},
      deleteNode: () => {},
      pickFiles: () => {},
      openPath: () => {},
      toast: () => {},
    }
  }
  return value
}
