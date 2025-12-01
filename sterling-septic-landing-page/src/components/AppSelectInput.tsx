import { Select } from 'flowbite-react';

const AppSelectInput = ({
    id,
    name,
    placeholder,
    options,
    required = false,
}: {
    id: string;
    name: string;
    placeholder: string;
    options: string[];
    required?: boolean;

}) => {
    return (
        <div className="max-w-md">
            <Select id={id} name={name} required={required}>
                <option value="">{placeholder}</option>
                {
                    options.map((option) => (
                        <option key={option} value={option}>{option}</option>
                    ))
                }
            </Select>
        </div>
    );
};

export default AppSelectInput;