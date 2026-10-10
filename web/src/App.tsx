import { strings } from './strings/vi.ts'

export function App() {
  return (
    <main className="w-full max-w-lg rounded-lg border border-slate-200 bg-white p-8 text-center shadow-xs dark:border-slate-700 dark:bg-slate-800">
      <h1 className="mb-4 text-2xl font-semibold text-slate-900 dark:text-slate-100">
        {strings.appName}
      </h1>
      <p className="text-base text-slate-600 dark:text-slate-400">
        {strings.statusUnderDevelopment}
      </p>
    </main>
  )
}

export default App
