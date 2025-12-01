import AppContainer from './AppContainer';
import { Button } from 'flowbite-react';
import { RightChevron } from './icons';
import InspectionImage from '../assets/images/image-5.png'

const InspectionSection = () => {
    return (
        <div className='bg-wave px-4 xl:px-0 py-8 md:py-12'>
            <AppContainer>
                <div className='flex flex-col md:flex-row items-center justify-between gap-4'>
                    <div>
                        <p className='uppercase text-2xl lg:text-4xl font-bold pb-4'>
                            <span className='text-custom-color'>$250 OFF</span> your home-sale <br /> septic inspection</p>
                        <p className='mb-4 text-lg lg:text-xl font-semibold'>We&apos;ll confirm eligibility when you call—book early <br /> so your RSS is filed on time.</p>
                        <Button href='#inspection-form' className='bg-custom-color-primary inline-flex items-center gap-2' size='xl' pill>
                            <span>BOOK MY INSPECTION</span>
                            <span className='bg-white inline-block p-2 rounded-full'>
                                <RightChevron width={14} height={14} />
                            </span>
                        </Button>
                    </div>
                    <div>
                        <img
                            src={InspectionImage}
                            alt="Inspection illustration"
                            className='responsive-image'
                        />
                    </div>
                </div>
            </AppContainer>
        </div>
    );
};

export default InspectionSection;