import AppModal from "./AppModal";
import { Phone } from "./icons";

const BookOverPhone = () => {
    return (
        <AppModal
            title="BOOK OVER PHONE"
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
                className="text-base lg:text-xl text-center font-semibold tracking-wider leading-loose"
            >
                Call/Text: <span className="text-custom-color">(253) 254-8630</span>
            </p>
        </AppModal>
    );
};

export default BookOverPhone;