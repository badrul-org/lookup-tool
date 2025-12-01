import AppDropdown from "./AppDropdown";
import { Phone } from "./icons";

const BookOverPhone2 = () => {
    return (
        <AppDropdown
            buttonText={
                <>
                    <Phone
                        width="24"
                        height="24"
                        fill="white"
                        className="me-2"
                    />
                    BOOK OVER PHONE
                </>
            }
        >
            <p
                className="text-base lg:text-xl text-center font-semibold "
            >
                <span>Call/Text:</span> <span className="text-custom-color">(253) 254-8630</span>
            </p>
        </AppDropdown>
    );
};

export default BookOverPhone2;