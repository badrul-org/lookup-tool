import { RiFacebookBoxFill, RiInstagramLine, RiLinkedinBoxFill, RiTwitterFill, } from "react-icons/ri";

const socialLinks = {
    facebook: "https://www.facebook.com",
    linkedin: "https://www.linkedin.com",
    instagram: "https://www.instagram.com",
    twitter: "https://www.twitter.com",
}

const ContactSection2 = () => {
    return (
        <div className="py-12 bg-custom-color-secondary flex items-center justify-center">
            <div className="flex flex-col gap-4 items-center justify-center">
                <div className="flex items-center justify-center gap-4">
                    <a href={socialLinks.facebook} className="flex justify-center items-center size-10 p-2 bg-white text-[#77b3db] rounded-md">
                        <RiFacebookBoxFill className="size-5" />
                    </a>
                    <a href={socialLinks.linkedin} className="flex justify-center items-center size-10 p-2 bg-white text-[#77b3db] rounded-md">
                        <RiLinkedinBoxFill className="size-5" />
                    </a>
                    <a href={socialLinks.instagram} className="flex justify-center items-center size-10 p-2 bg-white text-[#77b3db] rounded-md">
                        <RiInstagramLine className="size-5" />
                    </a>
                    <a href={socialLinks.twitter} className="flex justify-center items-center size-10 p-2 bg-white text-[#77b3db] rounded-md">
                        <RiTwitterFill className="size-5" />
                    </a>
                </div>
                <p className="text-white text-xl">(253) 254 8630</p>
                <p className="text-white text-xl">SterlingSepticandplumbing.com</p>
                <p className="text-white text-xl text-center">Serving Pierce and King Counties • <br /> Fast scheduling available</p>
            </div>
        </div>
    );
};

export default ContactSection2;