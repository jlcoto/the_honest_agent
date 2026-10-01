import { useEffect, useState } from 'react'

// Hash routes, so deep links keep working on any static host.
export type Route = { name: 'overview' } | { name: 'compare' } | { name: 'result'; resultId: string }

function parse(hash: string): Route {
  const [, name, id] = hash.replace(/^#/, '').split('/')
  if (name === 'compare') return { name: 'compare' }
  if (name === 'result' && id) return { name: 'result', resultId: decodeURIComponent(id) }
  return { name: 'overview' }
}

export function href(route: Route): string {
  if (route.name === 'compare') return '#/compare'
  if (route.name === 'result') return `#/result/${encodeURIComponent(route.resultId)}`
  return '#/'
}

export function navigate(route: Route) {
  window.location.hash = href(route)
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash))
  useEffect(() => {
    const onChange = () => {
      setRoute(parse(window.location.hash))
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
