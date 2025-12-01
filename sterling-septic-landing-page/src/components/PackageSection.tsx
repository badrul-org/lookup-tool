import AppContainer from './AppContainer';
import { TickCircle } from './icons';

const PackageSection = () => {
    return (
        <div className='mt-8 lg:mt-12'>
            <AppContainer>
                <h2 className='px-4 lg:px-0 font-bold tracking-wide text-xl lg:text-3xl mb-4'>Family-Backed Guarantee</h2>
            </AppContainer>
            <div className='bg-custom-color-secondary px-4 xl:px-0 py-8 md:py-12'>
                <AppContainer>
                    <h2 className='font-bold tracking-wide text-xl lg:text-3xl mb-4'>Our Home-Sale Package (built to prevent delays)</h2>
                    <ul className='flex flex-col gap-4 mt-6 lg:mt-8'>
                        <li className='flex items-center gap-2'>
                            <TickCircle className="size-8" />
                            <p className='text-lg lg:text-xl'>One call books your inspection and pumping.</p>
                        </li>
                        <li className='flex items-center gap-2'>
                            <TickCircle className="size-8" />
                            <p className='text-lg lg:text-xl'>Full photo documentation + We file the RSS for you.</p>
                        </li>
                        <li className='flex items-center gap-2'>
                            <TickCircle className="size-8" />
                            <p className='text-lg lg:text-xl'>Clear timelines and proactive status updates—no surprises.</p>
                        </li>
                    </ul>
                </AppContainer>
            </div>
        </div>
    );
};

export default PackageSection;