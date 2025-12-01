import { HourGlass, Tag } from "./icons";
import HeroImage from "../assets/images/image-6.png";
import { Button } from "flowbite-react";
import AppContainer from "./AppContainer";
import FormBookOnline2 from "./FormBookOnline2";
import BookOverPhone2 from "./BookOverPhone2";
import FormScheduleCall2 from "./FormScheduleCall2";
import { FaArrowTurnDown } from "react-icons/fa6";

const HeroContainer = () => {
    return (
        <div className="relative px-4 xl:px-0 py-8">
            <div className="bg-custom-color-secondary z-[-1] w-full h-full absolute top-0 left-0" />
            <AppContainer>
                <div className="grid grid-cols-1 md:grid-cols-2 items-start gap-4">
                    {/* right side section  */}
                    <div className="order-2 md:order-1">
                        <p className="text-2xl lg:text-3xl flex lg:items-center gap-1 mb-4">
                            <HourGlass width="32" height="32" fill="blue" />
                            Don't Run Out of Time!
                        </p>
                        <h1 className="text-center sm:text-start text-4xl lg:text-5xl font-semibold mb-4">
                            <span className="uppercase">
                                Take <span className="font-bold text-custom-color">$250 OFF</span>
                            </span>
                            <br />
                            Your Home-Sale
                            <br />
                            Septic Inspection
                        </h1>
                        <p className="text-white text-center sm:text-start text-lg lg:text-2xl mb-4">
                            Selling a home with a septic system? <br /> Avoid closing delays.
                        </p>
                        <div className="w-full h-[262px]">
                            <img
                                src={HeroImage}
                                className="w-full h-full object-cover object-top rounded-3xl shadow-lg"
                                alt="Hero Image"
                            />
                        </div>
                    </div>
                    {/* left side section  */}
                    <div id="inspection-form" className="relative order-1 md:order-2">
                        <div className="bg-white border-0 rounded-4xl shadow-lg p-5 relative md:absolute top-0 left-0 w-full z-10">
                            <div>
                                <div className="flex flex-row justify-between items-end mb-2">
                                    <FaArrowTurnDown className="text-custom-color rotate-y-180 size-10 lg:size-20 " />
                                    <div className="">
                                        <p className="font-bold text-2xl lg:text-4xl text-center mb-4">
                                            Schedule Your <br /> Inspection
                                        </p>
                                        <p className="text-custom-color text-base lg:text-xl text-center fs-5 fw-medium mb-4">
                                            Limited Time Offer
                                            <br />
                                            <span className="justify-center items-center flex gap-2">
                                                (Get In Touch)
                                            </span>
                                        </p>
                                    </div>
                                    <FaArrowTurnDown className="text-custom-color size-10 lg:size-20" />
                                </div>
                                <div className="grid grid-cols-1 gap-4">
                                    <FormBookOnline2 />

                                    <BookOverPhone2 />

                                    <FormScheduleCall2 />

                                    <Button type="button" size="xl" className="bg-custom-color-primary my-6 text-sm lg:text-base">
                                        <Tag width="24" height="24" fill="white" className="me-2" />
                                        CLAIM YOUR $250 OFF
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </AppContainer>
        </div>
    );
};

export default HeroContainer;