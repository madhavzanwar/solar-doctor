'use client'

import dynamic from 'next/dynamic'

const TrustStrip     = dynamic(() => import('./TrustStrip'),      { ssr: false })
const FeaturesGrid   = dynamic(() => import('./FeaturesGrid'),    { ssr: false })
const HowItWorks     = dynamic(() => import('./HowItWorks'),      { ssr: false })
const ContactSection = dynamic(() => import('./ContactSection'),  { ssr: false })
const Footer         = dynamic(() => import('./Footer'),          { ssr: false })

export default function DynamicSections() {
  return (
    <>
      <TrustStrip />
      <FeaturesGrid />
      <HowItWorks />
      <ContactSection />
      <Footer />
    </>
  )
}
