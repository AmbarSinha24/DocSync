import { useEffect, useState } from 'react'

const STORAGE_KEY = 'actor'
const DEFAULT_ACTOR = 'reviewer'

function getInitialActor() {
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_ACTOR
}

export function useActor() {
  const [actor, setActor] = useState(getInitialActor)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, actor)
  }, [actor])

  return { actor, setActor }
}
