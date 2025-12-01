import { Accordion, AccordionContent, AccordionPanel, AccordionTitle } from "flowbite-react";
import type { ReactNode } from "react";

const AppDropdown = ({
    buttonText,
    children
}: {
    buttonText: ReactNode;
    children: ReactNode
}) => {
    return (
        <Accordion collapseAll>
            <AccordionPanel>
                <AccordionTitle className="bg-custom-color-primary text-white rounded-lg">
                    <span className="text-white flex items-center gap-2 text-sm lg:text-base">
                        {buttonText}
                    </span>
                </AccordionTitle>
                <AccordionContent className="dark:bg-white">
                    {children}
                </AccordionContent>
            </AccordionPanel>
        </Accordion>
    );
};

export default AppDropdown;