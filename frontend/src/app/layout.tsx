import type { Metadata } from 'next'
import { JetBrains_Mono } from 'next/font/google'
import './globals.css'

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Enjin | Intelligence Engine',
  description:
    'Real-time OSINT intelligence platform with 3D globe visualization, entity tracking, and event correlation.',
  keywords: ['OSINT', 'intelligence', 'visualization', 'globe', 'entity tracking'],
  authors: [{ name: 'Enjin' }],
  themeColor: '#0a0a0f',
  viewport: 'width=device-width, initial-scale=1, maximum-scale=1',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${jetbrainsMono.variable} font-mono overflow-hidden`}
      >
        <div className="relative min-h-screen bg-enjin-dark bg-grid noise">
          {children}
        </div>
      </body>
    </html>
  )
}
