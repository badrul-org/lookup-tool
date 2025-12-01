import type { FormEvent, ReactNode } from "react";

type AppFormProps = {
    children: ReactNode;
    onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
    className?: string;
};

const AppForm = ({ children, onSubmit, className = "" }: AppFormProps) => {
    return (
        <form
            className={`flex max-w-md flex-col gap-4 ${className}`}
            onSubmit={onSubmit}
            noValidate
        >
            {children}
        </form>
    );
};

export default AppForm;