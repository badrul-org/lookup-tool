import { Button } from 'flowbite-react';
import AppContainer from './AppContainer';

const ClaimRewardSection = () => {
    return (
        <div className=" flex flex-col items-center justify-center bg-[#102E4A] py-8 text-center text-white">
            <AppContainer>
                <div className='flex flex-col items-center justify-center gap-4 '>
                    <h4 className='uppercase text-3xl lg:text-5xl font-semibold'>Claim your <span className='text-custom-color'>$250</span> off</h4>
                    <p className='text-lg'>and secure your closing date today!</p>
                    <Button href='#inspection-form' size='lg' className='bg-custom-color-primary' pill>Book Now!</Button>
                </div>
            </AppContainer>
        </div>
    );
};

export default ClaimRewardSection;