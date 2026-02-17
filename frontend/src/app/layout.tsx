import type { Metadata, Viewport } from 'next'
import './globals.css'

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  themeColor: '#0a0a0f',
}

export const metadata: Metadata = {
  title: 'Enjin | Intelligence Engine',
  description:
    'Real-time OSINT intelligence platform with 3D globe visualization, entity tracking, and event correlation.',
  keywords: ['OSINT', 'intelligence', 'visualization', 'globe', 'entity tracking'],
  authors: [{ name: 'Enjin' }],
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark">
      <body className="font-mono overflow-hidden">
        <div className="relative min-h-screen bg-enjin-dark bg-grid noise">
          {children}
        </div>
      </body>
    </html>
  )
}
