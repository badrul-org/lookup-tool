
const AppInput = ({
    id,
    name,
    placeholder,
    type = 'text',
    label = false,
    required = true,
}: {
    id: string;
    name: string;
    type?: string;
    placeholder: string;
    label?: string | boolean;
    required?: boolean;
}) => {
    return (
        <div>
            <div>
                {
                    label && (
                        <label
                            htmlFor={id}
                            className="block mb-2.5 text-sm font-medium text-heading">
                            {label}
                        </label>
                    )
                }

                <input
                    type={type}
                    name={name}
                    id={id}
                    className="bg-neutral-secondary-medium border border-default-medium text-heading text-sm rounded-md focus:ring-brand focus:border-brand block w-full px-3 py-2.5 shadow-xs placeholder:text-body"
                    placeholder={placeholder}
                    required={required} />
            </div>
        </div>
    );
};

export default AppInput;