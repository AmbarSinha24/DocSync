import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

const STORAGE_KEY = 'activeAddRepoJobId'
const POLL_INTERVAL_MS = 1500

const isFinished = (status) => status === 'done' || status === 'failed'

export function useAddRepoJob() {
  const [job, setJob] = useState(null)
  const intervalRef = useRef(null)

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const poll = useCallback(
    (jobId) => {
      stopPolling()
      intervalRef.current = setInterval(async () => {
        try {
          const result = await api.getRepoJob(jobId)
          setJob(result)
          if (isFinished(result.status)) {
            stopPolling()
            localStorage.removeItem(STORAGE_KEY)
          }
        } catch {
          stopPolling()
          localStorage.removeItem(STORAGE_KEY)
        }
      }, POLL_INTERVAL_MS)
    },
    [stopPolling],
  )

  const start = useCallback(
    async (url) => {
      const result = await api.addRepo(url)
      localStorage.setItem(STORAGE_KEY, String(result.id))
      setJob(result)
      if (!isFinished(result.status)) {
        poll(result.id)
      }
      return result
    },
    [poll],
  )

  const dismiss = useCallback(() => {
    stopPolling()
    localStorage.removeItem(STORAGE_KEY)
    setJob(null)
  }, [stopPolling])

  useEffect(() => {
    const storedId = localStorage.getItem(STORAGE_KEY)
    if (storedId) {
      api
        .getRepoJob(storedId)
        .then((result) => {
          setJob(result)
          if (isFinished(result.status)) {
            localStorage.removeItem(STORAGE_KEY)
          } else {
            poll(storedId)
          }
        })
        .catch(() => localStorage.removeItem(STORAGE_KEY))
    }
    return stopPolling
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { job, start, dismiss }
}
