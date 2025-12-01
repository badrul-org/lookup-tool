import { useState } from 'react';
import { Calender } from './icons';
import AppForm from './AppForm';
import AppInput from './AppInput';
import { Button } from 'flowbite-react';
import AppDropdown from './AppDropdown';

type SubmitState = 'idle' | 'loading' | 'success' | 'error';

const FormScheduleCall2 = () => {
    const [status, setStatus] = useState<SubmitState>('idle');
    const [message, setMessage] = useState<string>('');

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const form = event.currentTarget;
        setStatus('loading');
        setMessage('');

        const formData = new FormData(form);
        const payload = {
            full_name: (formData.get('name') || '').toString().trim(),
            phone: (formData.get('phone') || '').toString().trim(),
            email: (formData.get('email') || '').toString().trim(),
            address: (formData.get('address') || '').toString().trim(),
        };

        if (!payload.full_name || !payload.phone || !payload.email) {
            setStatus('error');
            setMessage('Name, phone, and email are required.');
            return;
        }

        try {
            const res = await fetch('/api/leads', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.error || 'Unable to save your request.');
            }

            setStatus('success');
            setMessage('Thanks! We received your request and will reach out shortly.');
            form.reset();
        } catch (error) {
            setStatus('error');
            setMessage(
                error instanceof Error ? error.message : 'Something went wrong. Please try again.'
            );
        } finally {
            setStatus((prev) => (prev === 'loading' ? 'idle' : prev));
        }
    };

    return (
        <AppDropdown
            buttonText={<>
                <Calender
                    width="24"
                    height="24"
                    fill="white"
                    className="me-2"
                />
                SCHEDULE A CALL
            </>}>
            <AppForm onSubmit={handleSubmit}>
                <AppInput
                    id='name'
                    name='name'
                    placeholder='Name'
                />
                <AppInput
                    id='phone'
                    name='phone'
                    placeholder='Phone'
                />
                <AppInput
                    id='email'
                    name='email'
                    placeholder='Email'
                />
                <AppInput
                    id='address'
                    name='address'
                    placeholder='Address'
                />
                <Button
                    type="submit"
                    className='bg-custom-color-primary uppercase'
                    disabled={status === 'loading'}
                >
                    <Calender
                        width="24"
                        height="24"
                        fill="white"
                        className="me-2"
                    />
                    {status === 'loading' ? 'Submitting...' : 'Schedule A Call'}
                </Button>
                {message && (
                    <p className={`text-sm ${status === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                        {message}
                    </p>
                )}
            </AppForm>
        </AppDropdown >
    );
};

export default FormScheduleCall2;