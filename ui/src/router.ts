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

// Links from outside (the Slack alert) use ?result=<id>: a sign-in in front of a hosted
// report redirects through its login and drops the #... part, but keeps the query.
function adoptResultQuery() {
  const params = new URLSearchParams(window.location.search)
  const resultId = params.get('result')
  if (!resultId) return
  params.delete('result')
  const query = params.toString()
  const url = window.location.pathname + (query ? `?${query}` : '') + href({ name: 'result', resultId })
  window.history.replaceState(null, '', url)
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => {
    adoptResultQuery()
    return parse(window.location.hash)
  })
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
