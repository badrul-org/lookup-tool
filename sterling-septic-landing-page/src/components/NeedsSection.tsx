import AppContainer from './AppContainer';
import { FormPen, Pumping } from './icons';

const NeedsSection = () => {
    return (
        <AppContainer>
            <h2 className='px-4 font-semibold text-2xl lg:text-3xl mt-8 mb-2 lg:mb-4'>Here's What You Will Need:</h2>
            <div className='grid items-start grid-cols-1 lg:grid-cols-3 gap-4'>
                <div className='flex flex-col items-center justify-center'>
                    <div className='w-24 h-24 bg-[#D9D9D9] flex items-center justify-center p-4 rounded-full'>
                        <FormPen width="84" height="84" />
                    </div>
                    <p className='text-2xl py-4 text-center'>Inspection</p>
                </div>
                <div className='flex flex-col items-center justify-center'>
                    <div className='w-24 h-24 bg-[#D9D9D9] flex items-center justify-center p-4 rounded-full'>
                        <Pumping width="84" height="84" />
                    </div>
                    <p className='text-2xl py-4 text-center'>Pumping</p>
                </div>
                <div className='flex flex-col items-center justify-center'>
                    <div className='w-24 h-24 bg-[#D9D9D9] flex items-center justify-center p-4 rounded-full'>
                        <FormPen width="84" height="84" />
                    </div>
                    <p className='text-2xl py-4 text-center'>RSS filling with <br /> the county</p>
                </div>
            </div>

        </AppContainer>
    );
};

export default NeedsSection;