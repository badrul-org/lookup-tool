import { ThemeInit } from "../.flowbite-react/init";
import AppNavbar from "./components/AppNavbar";
import ClaimRewardSection from "./components/ClaimRewardSection";
import ContactSection2 from "./components/ContactSection2";
// import ContactSection from "./components/ContactSection";
// import CoverImage from "./components/CoverImage";
import HeroContainer from "./components/HeroContainer";
import ImageGallery from "./components/ImageGallery";
import InspectionSection from "./components/InspectionSection";
import NeedsSection from "./components/NeedsSection";
import PackageSection from "./components/PackageSection";
import ServiceSection from "./components/ServiceSection";

export default function App() {

  return (
    <main className="max-w-[1440px] mx-auto">
      <ThemeInit />
      <AppNavbar />
      <HeroContainer />
      <NeedsSection />
      <InspectionSection />
      <ImageGallery />
      <ServiceSection />
      <PackageSection />
      <ClaimRewardSection />
      <ContactSection2 />
      {/* <CoverImage /> */}
      {/* <ContactSection /> */}
    </main>
  );
}
