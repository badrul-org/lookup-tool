import { Navbar, NavbarBrand, NavbarCollapse, NavbarLink, NavbarToggle } from "flowbite-react";
import AppContainer from "./AppContainer";

const AppNavbar = () => {
  return (
    <AppContainer>
      <Navbar fluid rounded className="dark:bg-white">
        <NavbarBrand>
          Home / Offer
        </NavbarBrand>
        <NavbarToggle />
        <NavbarCollapse>
          <NavbarLink
            href="#"
            className="dark:text-black md:dark:hover:text-gray-700">
            Services
          </NavbarLink>
          <NavbarLink
            href="#"
            className="dark:text-black md:dark:hover:text-gray-700">
            About Us
          </NavbarLink>
          <NavbarLink
            href="#"
            className="dark:text-black md:dark:hover:text-gray-700"
          >
            Contact
          </NavbarLink>
        </NavbarCollapse>
      </Navbar>
    </AppContainer>
  )
};

export default AppNavbar;
