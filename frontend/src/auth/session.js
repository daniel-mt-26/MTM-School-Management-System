export function createSingleFlight(loader) {
  let inFlight = null

  return () => {
    if (!inFlight) {
      inFlight = Promise.resolve()
        .then(loader)
        .finally(() => { inFlight = null })
    }
    return inFlight
  }
}
