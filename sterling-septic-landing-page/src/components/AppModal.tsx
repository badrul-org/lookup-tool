import { Button, Modal, ModalBody, ModalHeader } from "flowbite-react";
import { useState, type ReactNode } from "react"

const AppModal = ({
    title,
    buttonText,
    children
}: {
    title: string;
    buttonText: ReactNode;
    children: ReactNode
}) => {
    const [openModal, setOpenModal] = useState(false);

    function onCloseModal() {
        setOpenModal(false);
    }

    return (
        <>
            <Button
                onClick={() => setOpenModal(true)} className="bg-custom-color-primary"
                type="button"
                size="lg"
            >
                {buttonText}
            </Button>

            <Modal
                show={openModal}
                size="md"
                onClose={onCloseModal}
                
            >
                <ModalHeader id="modal-header" className="dark:bg-white">
                    {title}
                </ModalHeader>
                <ModalBody className="dark:bg-white">
                    {children}
                </ModalBody>
            </Modal>
        </>
    );
};

export default AppModal;