import { strings } from './strings/vi.ts'

export function App() {
  return (
    <main className="dashboard-container">
      <h1>{strings.appName}</h1>
      <p className="status-line">{strings.statusUnderDevelopment}</p>
    </main>
  )
}

export default App
