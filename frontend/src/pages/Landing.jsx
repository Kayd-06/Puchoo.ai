import Loader from '../components/landing/Loader';
import Navbar from '../components/landing/Navbar';
import Hero from '../components/landing/Hero';
import {
  About,
  BuiltWith,
  Capabilities,
  Examples,
  Faq,
  FinalCta,
  Footer,
  HowItWorks,
  Principle,
  Security,
} from '../components/landing/Sections';
import { focusRing } from '../components/landing/ui';

export default function Landing() {
  return (
    <div className="site bg-[#05080c] text-[#111827]">
      <title>Puchoo.ai · Multilingual Text-to-SQL</title>
      <a
        href="#main"
        className={`sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[80] focus:rounded-full focus:bg-white focus:px-4 focus:py-2 ${focusRing}`}
      >
        Skip to content
      </a>
      <Loader />
      <Navbar />
      <main id="main">
        <Hero />
        <About />
        <BuiltWith />
        <Principle />
        <Capabilities />
        <HowItWorks />
        <Security />
        <Examples />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </div>
  );
}
