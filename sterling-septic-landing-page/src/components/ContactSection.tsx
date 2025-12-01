import AppContainer from "./AppContainer";

const ContactSection = () => {
    return (
        <AppContainer>
            <div className="px-4 flex items-center justify-center">
                <p className="font-light text-lg lg:text-2xl pb-4">
                    Call/Text: (253) 254-8630 • SterlingSepticandplumbing.com
                    <br />
                    Serving Pierce and King Counties • Fast scheduling available
                    <br />
                    P.S. The clock is ticking on RSS processing.
                    <br />
                    Claim your $250 OFF and secure your closing date today!
                </p>
            </div>
            <p
                className="text-base lg:text-xl pb-8 text-center">
                @allrightsreserved_SterlingSeptic
            </p>
        </AppContainer>
    );
};

export default ContactSection;