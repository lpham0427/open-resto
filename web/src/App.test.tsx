import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App.tsx'
import { strings } from './strings/vi.ts'

describe('App', () => {
  it('renders application name heading and under development status', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { level: 1, name: strings.appName }),
    ).toBeInTheDocument()
    expect(screen.getByText(strings.statusUnderDevelopment)).toBeInTheDocument()
  })
})
