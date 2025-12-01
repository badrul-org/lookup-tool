import AppContainer from './AppContainer';
import { Family, License, Services } from './icons';

const ServiceSection = () => {
    return (
        <AppContainer>
            <div className='grid grid-cols-12 gap-4 px-4 lg:px-0 my-10'>
                <div className='col-span-12 lg:col-span-8'>
                    <h2 className='uppercase text-3xl font-semibold mb-4'>Why Sterling Septic?</h2>
                    <p className='text-lg mb-4'>We&apos;re one of the few truly family-owned and operated septic companies in the area. Our family name is on every job—expect real customer service, clear communication, and care for your home and timeline.</p>
                </div>
                <div className='col-span-12 lg:col-span-4'>
                    <div className='flex flex-col gap-4'>
                        <div className='flex items-center gap-2 lg:gap-4'>
                            <Family className="size-8 lg:size-10" />
                            <h3 className='text-lg lg:text-xl'>Family Owned</h3>
                        </div>
                        <div className='flex items-center gap-2 lg:gap-4'>
                            <License className="size-8 lg:size-10" />
                            <h3 className='text-lg lg:text-xl'>Licensed and Certified</h3>
                        </div>
                        <div className='flex items-center gap-2 lg:gap-4'>
                            <Services className="size-8 lg:size-10" />
                            <h3 className='text-lg lg:text-xl'>Real customer service</h3>
                        </div>
                    </div>
                </div>
            </div>
            <p className='px-4 lg:px-0 text-lg lg:text-xl mb-4 tracking-wider'>In the unlikely event we miss a step, we fix it fast and expedite at our cost.</p>
        </AppContainer>
    );
};

export default ServiceSection;