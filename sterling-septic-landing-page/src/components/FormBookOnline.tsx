import { useState } from 'react';
import { Button } from 'flowbite-react';
import AppForm from './AppForm';
import AppInput from './AppInput';
import AppModal from './AppModal';
import { Badge } from './icons';

type SubmitState = 'idle' | 'loading' | 'success' | 'error';

const FormBookOnline = () => {
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
            system_type: (formData.get('typeOfSystem') || '').toString().trim(),
            digging_needed: (formData.get('diggingNeeded') || '').toString().trim(),
            obstacles: (formData.get('thingOverTheTank') || '').toString().trim(),
            service_timeline: (formData.get('serviceTimeline') || '').toString().trim(),
            service_needed: (formData.get('septicService') || '').toString().trim(),
            contact_preference: (formData.get('connectionInfo') || '').toString().trim(),
            referral_source: (formData.get('hearAboutUs') || '').toString().trim(),
            household_size: (formData.get('numberOfPeople') || '').toString().trim(),
            additional_notes: (formData.get('anyOfTheFollowing') || '').toString().trim(),
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
            setMessage('Thanks! We received your booking request and will follow up shortly.');
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
        <AppModal
            title='BOOK ONLINE'
            buttonText={<>
                <Badge
                    width="24"
                    height="24"
                    fill="white"
                    className="me-2"
                />
                BOOK ONLINE
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
                <AppInput
                    id='typeOfSystem'
                    name='typeOfSystem'
                    placeholder='Type Of System'
                />
                <AppInput
                    id='diggingNeeded'
                    name='diggingNeeded'
                    placeholder='Is Digging Needed'
                />
                <AppInput
                    id='thingOverTheTank'
                    name='thingOverTheTank'
                    placeholder='Anything Over The Tank/Components Other Than Dirt? Example: Tank Under Deck, Tank In Crawlspace?'
                />
                <AppInput
                    id='serviceTimeline'
                    name='serviceTimeline'
                    placeholder='Service Timeline'
                />
                <AppInput
                    id='septicService'
                    name='septicService'
                    placeholder='What Septic Service Is Needed?'
                />
                <AppInput
                    id='connectionInfo'
                    name='connectionInfo'
                    placeholder='How Can We Connect?'
                />
                <AppInput
                    id='hearAboutUs'
                    name='hearAboutUs'
                    placeholder='How Did You Hear About Us?'
                />
                <AppInput
                    id='numberOfPeople'
                    name='numberOfPeople'
                    placeholder='Number Of People In Home?'
                />
                <AppInput
                    id='anyOfTheFollowing'
                    name='anyOfTheFollowing'
                    placeholder='Any Of The Following'
                />
                <Button
                    type="submit"
                    className='bg-custom-color-primary'
                    disabled={status === 'loading'}
                >
                    <Badge
                        width="24"
                        height="24"
                        fill="white"
                        className="me-2"
                    />
                    {status === 'loading' ? 'Submitting...' : 'BOOK ONLINE'}
                </Button>
                {message && (
                    <p className={`text-sm ${status === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                        {message}
                    </p>
                )}
            </AppForm>
        </AppModal >
    );
};

export default FormBookOnline;

