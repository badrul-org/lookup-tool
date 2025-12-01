import Image1 from '../assets/images/image-3.png';
import Image2 from '../assets/images/image-4.png';
import Image3 from '../assets/images/image-2.jpg';
import AppContainer from './AppContainer';

const ImageGallery = () => {
    return (
        <AppContainer >
            <div className='grid grid-cols-1 place-items-center lg:grid-cols-3 gap-4 py-12 px-4 lg:px-0'>
                <img
                    src={Image1}
                    alt="Image 1"
                    width={400}
                    height={400}
                    className='mask1 responsive-image'
                />
                <img
                    src={Image2}
                    alt="Image 2"
                    width={400}
                    height={400}
                    className='mask2 responsive-image'
                />
                <img
                    src={Image3}
                    alt="Image 3"
                    width={400}
                    height={400}
                    className='mask2 responsive-image'
                />
            </div>
        </AppContainer>
    );
};

export default ImageGallery;