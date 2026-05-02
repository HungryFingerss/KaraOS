import type { Metadata } from 'next'
import { Space_Mono, Syne } from 'next/font/google'
import './globals.css'

const mono = Space_Mono({
  subsets: ['latin'],
  weight: ['400', '700'],
  variable: '--font-mono',
})

const display = Syne({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-display',
})

export const metadata: Metadata = {
  title: 'DOG-AI',
  description: 'Face recognition pipeline dashboard',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${mono.variable} ${display.variable}`}>
      <body className="bg-night text-white font-mono antialiased min-h-screen">
        {children}
      </body>
    </html>
  )
}
